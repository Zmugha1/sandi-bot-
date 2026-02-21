"""
Ollama multimodal extraction fallback for scanned/image PDFs.
Renders PDF pages to images, calls Ollama vision API, returns facts in same format as extract_pdf.
Fully local (localhost:11434). No cloud.
"""
import json
import re
import base64
from typing import Dict, List, Any, Optional, Tuple

from . import schemas as sch

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_CHAT = f"{OLLAMA_BASE}/api/chat"
BATCH_PAGES = 3
RENDER_DPI = 150

SYSTEM_PROMPT = """You are an information extraction engine. Return ONLY valid JSON. No commentary, no markdown, no explanation."""

USER_PROMPT_TEMPLATE = """Extract career-fit relevant insights from this personality report page image.
Return JSON with exactly these keys:
{
  "traits_do": ["short phrase 3-12 words", ...],
  "traits_dont": ["short phrase", ...],
  "drivers": [{"label": "Driver name", "score": 0}, ...],
  "risks": ["short phrase", ...],
  "evidence_quotes": [{"page": 1, "quote": "exact short quote from the page"}]
}
Rules:
- Use short phrases (3-12 words).
- Do not invent facts not visible in the image.
- If a key is not present on the page, return an empty list [].
- evidence_quotes must include at least 1 quote from the page if possible.
- Page number in evidence_quotes must be the page number given below.
Return only the JSON object, no other text."""

STRICT_RETRY_PROMPT = """Return ONLY a JSON object. No text before or after. Keys: traits_do, traits_dont, drivers, risks, evidence_quotes. Each value must be a list."""


def render_pdf_to_images(pdf_bytes: bytes, dpi: int = RENDER_DPI) -> List[Tuple[int, bytes]]:
    """
    Render each PDF page to PNG bytes. Returns list of (page_number, png_bytes).
    """
    if not HAS_FITZ or not pdf_bytes:
        return []
    out: List[Tuple[int, bytes]] = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for i in range(len(doc)):
            page_num = i + 1
            page = doc.load_page(i)
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png_bytes = pix.tobytes("png")
            out.append((page_num, png_bytes))
        doc.close()
    except Exception:
        pass
    return out


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Try to parse JSON from model output (may be wrapped in markdown or extra text)."""
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    # Strip markdown code block if present
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def call_ollama_vision(
    images_by_page: List[Tuple[int, bytes]],
    model_name: str,
    user_prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
) -> Optional[Dict[str, Any]]:
    """
    Send 1 image (or batch) to Ollama chat API with vision.
    images_by_page: list of (page_num, png_bytes).
    Returns parsed JSON dict or None.
    """
    if not HAS_REQUESTS or not images_by_page or not model_name:
        return None
    # Ollama /api/chat: user message has "content" (text) and "images" (array of base64 strings)
    images_b64 = [base64.b64encode(png_bytes).decode("ascii") for _, png_bytes in images_by_page]
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt, "images": images_b64},
        ],
        "stream": False,
    }
    try:
        r = requests.post(OLLAMA_CHAT, json=payload, timeout=120)
        if r.status_code != 200:
            return None
        data = r.json()
        msg = data.get("message") or {}
        raw = msg.get("content") or ""
        return _extract_json_from_text(raw)
    except Exception:
        return None


def extract_facts_ollama(
    pdf_bytes: bytes,
    client_name: str,
    doc_id: str,
    model_name: str = "llava",
) -> Dict[str, Any]:
    """
    Render PDF to images, call Ollama per batch, aggregate facts.
    Returns same structure as extract_pdf.extract_facts(): client_name, doc_id, facts[], extraction_status, etc.
    """
    result = {
        "client_name": client_name,
        "doc_id": doc_id,
        "facts": [],
        "total_chars_extracted": 0,
        "pages_with_text_count": 0,
        "extraction_status": "text_extraction_failed",
        "headings_found": 0,
        "bullets_found": 0,
        "do_lines_found_count": 0,
        "dont_lines_found_count": 0,
        "facts_count_by_type": {},
        "extraction_message": None,
    }
    if not HAS_FITZ:
        result["extraction_message"] = "PyMuPDF required for PDF rendering. Install pymupdf."
        return result
    if not HAS_REQUESTS:
        result["extraction_message"] = "requests required for Ollama. Install requests."
        return result

    pages_images = render_pdf_to_images(pdf_bytes)
    if not pages_images:
        result["extraction_message"] = "Could not render PDF to images."
        return result

    result["pages_with_text_count"] = len(pages_images)
    all_facts: List[Dict[str, Any]] = []
    seen_labels: set = set()

    # Batch 1..BATCH_PAGES pages at a time
    for i in range(0, len(pages_images), BATCH_PAGES):
        batch = pages_images[i : i + BATCH_PAGES]
        page_nums = [p[0] for p in batch]
        default_page = page_nums[0] if page_nums else 1
        user_text = user_prompt_for_batch(page_nums)
        parsed = call_ollama_vision(batch, model_name, user_text)
        if not parsed:
            parsed = call_ollama_vision(batch, model_name, STRICT_RETRY_PROMPT + f"\nPage(s): {page_nums}")
        if parsed:
            validated = sch.validate_ollama_response(parsed)
            # Ensure evidence_quotes have page set
            eq_list = validated.get("evidence_quotes") or []
            for idx, eq in enumerate(eq_list):
                if isinstance(eq, dict) and eq.get("page") is None:
                    eq["page"] = default_page
                elif not isinstance(eq, dict):
                    eq_list[idx] = {"page": default_page, "quote": _get(eq, "quote", "")}
            facts_batch = sch.ollama_response_to_facts(validated, default_page=default_page)
            for f in facts_batch:
                label = (f.get("label") or "").strip()
                if label and label not in seen_labels:
                    seen_labels.add(label)
                    all_facts.append(f)

    if not all_facts:
        result["extraction_message"] = "Ollama returned no valid facts. Check model supports vision and try again."
        return result

    result["facts"] = all_facts[:80]
    result["extraction_status"] = "ok"
    result["extraction_message"] = None
    result["total_chars_extracted"] = 0  # N/A for image extraction
    for f in result["facts"]:
        t = f.get("type") or "unknown"
        result["facts_count_by_type"][t] = result["facts_count_by_type"].get(t, 0) + 1
    return result


def user_prompt_for_batch(page_nums: List[int]) -> str:
    """Build user prompt with page number(s) for evidence_quotes."""
    pages_str = ", ".join(str(p) for p in page_nums)
    return USER_PROMPT_TEMPLATE + f"\n\nPage number(s) for this image: {pages_str}."


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def ollama_available() -> bool:
    """Check if Ollama is running on localhost:11434."""
    if not HAS_REQUESTS:
        return False
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False
