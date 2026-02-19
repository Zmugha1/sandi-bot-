"""
Deterministic extraction of personality insights from PDF.
Uses PyMuPDF (fitz) or pdfplumber. No LLM. Output: structured facts with evidence (page, snippet).
"""
import re
from typing import List, Dict, Any, Optional

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

# Section headings to look for (case-insensitive)
SECTION_HEADINGS = [
    "behavioral", "driving forces", "communication", "strengths",
    "areas for improvement", "checklist", "motivators", "preferences",
    "do's and don'ts", "do and don't", "key traits", "risks",
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
DO_DONOT_PATTERNS = [
    r"do\s*:\s*([^\n]+)",
    r"don'?t\s*:\s*([^\n]+)",
    r"^\s*[-*]\s+(do|don't)\s+([^\n]+)",
    r"^\s*[-*]\s+([^.\n]+)",  # bullet
]


def _extract_text_by_page_pymupdf(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    pages = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for i in range(len(doc)):
        page_num = i + 1
        block = doc.load_page(i)
        text = block.get_text()
        pages.append({"page": page_num, "text": text})
    doc.close()
    return pages


def _extract_text_by_page_pdfplumber(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    import io
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


def _find_phrase_matches(text: str, patterns: List[str]) -> List[str]:
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            phrase = (m.group(1) or m.group(2) if m.lastindex >= 2 else m.group(1)).strip()
            if len(phrase) > 3 and len(phrase) < 150 and phrase not in found:
                found.append(phrase)
    return found


def _extract_bullets(text: str, max_len: int = 120) -> List[str]:
    bullets = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 4:
            continue
        # bullet or numbered
        if re.match(r"^[-*•]\s+", line) or re.match(r"^\d+[.)]\s+", line):
            content = re.sub(r"^[-*•]\s+", "", re.sub(r"^\d+[.)]\s+", "", line))
            if 4 <= len(content) <= max_len and content not in bullets:
                bullets.append(content)
    return bullets[:30]


def _snippet(text: str, max_chars: int = 200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rsplit(" ", 1)[0] + "..."


def extract_facts(client_name: str, doc_id: str, pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Deterministic extraction. Returns:
    {
      "client_name": ...,
      "doc_id": ...,
      "facts": [ {"type": "trait"|"driver"|"risk"|"communication_do"|"communication_dont"|"risk", "label": ..., "evidence": {"page": N, "snippet": ...}}, ... ]
    }
    """
    pages = extract_text_by_page(pdf_bytes)
    full_text = "\n\n".join(p["text"] for p in pages)
    facts = []

    for page_blob in pages:
        page_num = page_blob["page"]
        text = page_blob["text"]
        if not text.strip():
            continue

        # Traits
        for phrase in _find_phrase_matches(text, TRAIT_PATTERNS):
            facts.append({
                "type": "trait",
                "label": phrase,
                "evidence": {"page": page_num, "snippet": _snippet(phrase + " " + text[:100])},
            })
        # Drivers
        for phrase in _find_phrase_matches(text, DRIVER_PATTERNS):
            facts.append({
                "type": "driver",
                "label": phrase,
                "evidence": {"page": page_num, "snippet": _snippet(phrase + " " + text[:100])},
            })
        # Risks / avoid
        for phrase in _find_phrase_matches(text, RISK_PATTERNS):
            facts.append({
                "type": "risk",
                "label": phrase,
                "evidence": {"page": page_num, "snippet": _snippet(phrase + " " + text[:100])},
            })

        # Bullets under a "communication" or "do/don't" context
        lower = text.lower()
        if "communication" in lower or "do" in lower or "don't" in lower:
            for bullet in _extract_bullets(text):
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

    # If no pattern-based facts, use first few bullets as generic traits
    if not facts and pages:
        for page_blob in pages[:5]:
            for bullet in _extract_bullets(page_blob["text"])[:10]:
                facts.append({
                    "type": "trait",
                    "label": bullet,
                    "evidence": {"page": page_blob["page"], "snippet": _snippet(bullet)},
                })

    return {
        "client_name": client_name,
        "doc_id": doc_id,
        "facts": facts[:80],
    }
