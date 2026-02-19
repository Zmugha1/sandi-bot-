"""
Deterministic extraction of personality insights from PDF.
Uses PyMuPDF first; fallback to pdfplumber if low char count. No LLM.
Output: structured facts with evidence (page, snippet) and debug counters.
"""
import re
import io
from typing import List, Dict, Any, Optional, Tuple

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

MIN_CHARS_OK = 1500  # Below this, try fallback or report text_extraction_failed

# Section headings (TTI / Talent Insights style, case-insensitive)
SECTION_HEADINGS = [
    "behavioral", "driving forces", "communication", "strengths",
    "areas for improvement", "checklist", "motivators", "preferences",
    "do's and don'ts", "do and don't", "key traits", "risks",
    "tti", "talent insights", "disc", "behavioral traits", "work style",
    "communication style", "motivators and preferences",
]

# Keyword patterns that suggest trait/driver/risk phrases
TRAIT_PATTERNS = [
    r"tends to\s+([^.\n]+)",
    r"prefers\s+([^.\n]+)",
    r"often\s+([^.\n]+)",
    r"typically\s+([^.\n]+)",
    r"likes to\s+([^.\n]+)",
]
DRIVER_PATTERNS = [
    r"motivated by\s+([^.\n]+)",
    r"driven by\s+([^.\n]+)",
    r"values\s+([^.\n]+)",
    r"needs\s+([^.\n]+)",
]
RISK_PATTERNS = [
    r"avoid[s]?\s+([^.\n]+)",
    r"avoids\s+([^.\n]+)",
    r"risk[s]?\s*:\s*([^.\n]+)",
    r"watch (?:out|for)\s+([^.\n]+)",
    r"tendency to\s+([^.\n]+)",
]


def _extract_text_by_page_pymupdf(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    pages = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for i in range(len(doc)):
        page_num = i + 1
        block = doc.load_page(i)
        text = block.get_text()
        pages.append({"page": page_num, "text": text or ""})
    doc.close()
    return pages


def _extract_text_by_page_pdfplumber(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, p in enumerate(pdf.pages):
            text = p.extract_text() or ""
            pages.append({"page": i + 1, "text": text})
    return pages


def extract_text_by_page(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    if HAS_FITZ:
        return _extract_text_by_page_pymupdf(pdf_bytes)
    if HAS_PDFPLUMBER:
        return _extract_text_by_page_pdfplumber(pdf_bytes)
    raise RuntimeError("Install pymupdf or pdfplumber for PDF extraction.")


def _count_headings(full_text: str) -> int:
    lower = full_text.lower()
    return sum(1 for h in SECTION_HEADINGS if h in lower)


def _find_phrase_matches(text: str, patterns: List[str]) -> List[str]:
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            phrase = (m.group(1) or (m.group(2) if m.lastindex >= 2 else "")).strip()
            if len(phrase) > 3 and len(phrase) < 150 and phrase not in found:
                found.append(phrase)
    return found


def _extract_bullets(text: str, max_len: int = 120) -> List[str]:
    bullets = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 4:
            continue
        if re.match(r"^[-*•]\s+", line) or re.match(r"^\d+[.)]\s+", line):
            content = re.sub(r"^[-*•]\s+", "", re.sub(r"^\d+[.)]\s+", "", line))
            if 4 <= len(content) <= max_len and content not in bullets:
                bullets.append(content)
    return bullets[:30]


def _snippet(text: str, max_chars: int = 200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rsplit(" ", 1)[0] + "..." if max_chars > 3 else text[:max_chars]


def _extract_facts_from_pages(
    pages: List[Dict[str, Any]],
    client_name: str,
    doc_id: str,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Run pattern + bullet extraction. Returns (facts, headings_found, bullets_found)."""
    full_text = "\n\n".join(p.get("text", "") for p in pages)
    headings_found = _count_headings(full_text)
    bullets_found = 0
    facts = []

    for page_blob in pages:
        page_num = page_blob["page"]
        text = page_blob["text"] or ""
        if not text.strip():
            continue

        for phrase in _find_phrase_matches(text, TRAIT_PATTERNS):
            facts.append({
                "type": "trait",
                "label": phrase,
                "evidence": {"page": page_num, "snippet": _snippet(phrase + " " + text[:100])},
            })
        for phrase in _find_phrase_matches(text, DRIVER_PATTERNS):
            facts.append({
                "type": "driver",
                "label": phrase,
                "evidence": {"page": page_num, "snippet": _snippet(phrase + " " + text[:100])},
            })
        for phrase in _find_phrase_matches(text, RISK_PATTERNS):
            facts.append({
                "type": "risk",
                "label": phrase,
                "evidence": {"page": page_num, "snippet": _snippet(phrase + " " + text[:100])},
            })

        lower = text.lower()
        if "communication" in lower or "do" in lower or "don't" in lower:
            for bullet in _extract_bullets(text):
                bullets_found += 1
                if any(w in bullet.lower() for w in ["avoid", "don't", "do not"]):
                    facts.append({
                        "type": "communication_dont",
                        "label": bullet,
                        "evidence": {"page": page_num, "snippet": _snippet(bullet)},
                    })
                else:
                    facts.append({
                        "type": "communication_do",
                        "label": bullet,
                        "evidence": {"page": page_num, "snippet": _snippet(bullet)},
                    })
        else:
            for bullet in _extract_bullets(text):
                bullets_found += 1

    if not facts and pages:
        for page_blob in pages[:5]:
            for bullet in _extract_bullets(page_blob["text"])[:10]:
                bullets_found += 1
                facts.append({
                    "type": "trait",
                    "label": bullet,
                    "evidence": {"page": page_blob["page"], "snippet": _snippet(bullet)},
                })
    return facts[:80], headings_found, bullets_found


def extract_facts(client_name: str, doc_id: str, pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Deterministic extraction. Tries PyMuPDF first; if total_chars < MIN_CHARS_OK, tries pdfplumber.
    If still low, returns extraction_status="text_extraction_failed", facts=[], and a clear message.
    Returns:
      client_name, doc_id, facts[],
      total_chars_extracted, pages_with_text_count, extraction_status (ok | fallback_used | text_extraction_failed),
      headings_found, bullets_found, facts_count_by_type
    """
    status = "ok"
    pages = []
    if HAS_FITZ:
        pages = _extract_text_by_page_pymupdf(pdf_bytes)
    elif HAS_PDFPLUMBER:
        pages = _extract_text_by_page_pdfplumber(pdf_bytes)
    else:
        return {
            "client_name": client_name,
            "doc_id": doc_id,
            "facts": [],
            "total_chars_extracted": 0,
            "pages_with_text_count": 0,
            "extraction_status": "text_extraction_failed",
            "headings_found": 0,
            "bullets_found": 0,
            "facts_count_by_type": {},
            "extraction_message": "No PDF library available. Install pymupdf or pdfplumber.",
        }

    total_chars = sum(len(p.get("text", "")) for p in pages)
    pages_with_text = sum(1 for p in pages if (p.get("text") or "").strip())

    if total_chars < MIN_CHARS_OK and HAS_PDFPLUMBER and HAS_FITZ:
        pages = _extract_text_by_page_pdfplumber(pdf_bytes)
        total_chars = sum(len(p.get("text", "")) for p in pages)
        pages_with_text = sum(1 for p in pages if (p.get("text") or "").strip())
        status = "fallback_used"

    if total_chars < MIN_CHARS_OK:
        return {
            "client_name": client_name,
            "doc_id": doc_id,
            "facts": [],
            "total_chars_extracted": total_chars,
            "pages_with_text_count": pages_with_text,
            "extraction_status": "text_extraction_failed",
            "headings_found": 0,
            "bullets_found": 0,
            "facts_count_by_type": {},
            "extraction_message": (
                "This PDF appears to be scanned images; text extraction returned near-zero. "
                "Please upload a text-based PDF."
            ),
        }

    facts, headings_found, bullets_found = _extract_facts_from_pages(pages, client_name, doc_id)
    facts_count_by_type = {}
    for f in facts:
        t = f.get("type") or "unknown"
        facts_count_by_type[t] = facts_count_by_type.get(t, 0) + 1

    return {
        "client_name": client_name,
        "doc_id": doc_id,
        "facts": facts,
        "total_chars_extracted": total_chars,
        "pages_with_text_count": pages_with_text,
        "extraction_status": status,
        "headings_found": headings_found,
        "bullets_found": bullets_found,
        "facts_count_by_type": facts_count_by_type,
        "extraction_message": None,
    }
