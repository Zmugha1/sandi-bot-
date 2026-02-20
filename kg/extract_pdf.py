"""
Deterministic extraction of personality insights from PDF.
Uses PyMuPDF first; fallback to pdfplumber if low char count. No LLM.
Evidence snippets are cleaned and filtered for demo-ready display.
"""
import re
import io
from typing import List, Dict, Any, Optional, Tuple

from . import clean_text as ct

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

# Section headings for bullet extraction (TTI / Talent Insights style)
SECTION_HEADINGS = [
    "behavioral", "driving forces", "communication", "strengths",
    "areas for improvement", "checklist", "motivators", "preferences",
    "do's and don'ts", "do and don't", "key traits", "risks",
    "tti", "talent insights", "disc", "behavioral traits", "work style",
    "communication style", "motivators and preferences",
]
BULLET_HEADINGS = [
    "checklist for communicating",
    "behavioral characteristics",
    "strengths",
    "areas for improvement",
    "driving forces",
]

# Keyword patterns that suggest trait/driver/risk phrases (no often/typically - unreliable fragments)
TRAIT_PATTERNS = [
    r"tends to\s+([^.\n]+)",
    r"prefers\s+([^.\n]+)",
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

# Boilerplate to strip from labels/evidence
_BOILERPLATE_PHRASES = [
    re.compile(r"Behavioral\s+Characteristics\s+Based\s+on\s+[\w\s]+\'s\s+responses[.,]?\s*", re.IGNORECASE),
    re.compile(r"Based\s+on\s+[\w\s]+\'s\s+responses[.,]?\s*", re.IGNORECASE),
    re.compile(r"the\s+report\s+has\s+selected\s+general\s+statements[.,]?\s*", re.IGNORECASE),
]


def _clean_line(s: str) -> str:
    """Normalize whitespace and remove repeating boilerplate phrases."""
    if not s or not isinstance(s, str):
        return ""
    out = re.sub(r"\s+", " ", s).strip()
    for pat in _BOILERPLATE_PHRASES:
        out = pat.sub("", out).strip()
    return out


def _is_bad_fragment(s: str) -> bool:
    """Return True if label/snippet should be rejected (junk or fragment)."""
    if not s or not isinstance(s, str):
        return True
    s = s.strip()
    if len(s) < 8:
        return True
    if not re.search(r"[a-zA-Z]", s):
        return True
    is_do_dont = bool(re.match(r"^(?:Do|Don\'t|DON\'T|Dont)\s*:\s*", s, re.IGNORECASE))
    if s[0].islower() and not is_do_dont:
        return True
    if "based on" in s.lower() and len(s) < 120:
        return True
    if ("mask some of" in s.lower() or "working as" in s.lower()):
        if len(s) < 80 or s[-1] not in ".!?":
            return True
    return False


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


def _extract_do_dont_lines(text: str) -> List[Tuple[str, str]]:
    """
    Extract Do:/Don't: lines (TTI reports). Returns List[(type, label)].
    type is 'trait_do' or 'trait_dont'; label is clean text after colon (e.g. 'Do: People-oriented.').
    Min 8, max 140 chars. Captures guidance like "Provide 'yes' or 'no' answers—not maybe." as Do: line.
    """
    out: List[Tuple[str, str]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or len(raw) < 8:
            continue
        # Do: (including "Do's:" and "Do :")
        m_do = re.match(r"^(?:Do\'?s?|Do)\s*:\s*(.+)", raw, re.IGNORECASE)
        # Don't: / Dont: / Do not:
        m_dont = re.match(r"^(?:Don\'t|DON\'T|Dont|Do\s+not)\s*:\s*(.+)", raw, re.IGNORECASE)
        if m_dont:
            content = _clean_line(m_dont.group(1).strip())
            if not content or _is_bad_fragment(content):
                continue
            label = "Don't: " + content
            if 8 <= len(label) <= 140:
                out.append(("trait_dont", label))
            continue
        if m_do:
            content = _clean_line(m_do.group(1).strip())
            if not content or _is_bad_fragment(content):
                continue
            label = "Do: " + content
            if 8 <= len(label) <= 140:
                out.append(("trait_do", label))
    return out


def _is_heading_line(line_lower: str) -> bool:
    return any(h in line_lower for h in BULLET_HEADINGS)


def _is_bullet_line(line: str) -> bool:
    s = line.strip()
    return bool(re.match(r"^[-*•]\s+", s) or re.match(r"^\d+[.)]\s+", s))


def _extract_bullets_under_headings(text: str, max_len: int = 150) -> List[tuple]:
    """Return list of (content, is_under_communicating) for bullets under BULLET_HEADINGS."""
    lines = text.splitlines()
    out = []
    in_section = False
    last_heading_was_comm = False
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if _is_heading_line(lower):
            in_section = True
            last_heading_was_comm = "communicat" in lower or "checklist" in lower
            continue
        if in_section and _is_bullet_line(line):
            content = re.sub(r"^[-*•]\s+", "", re.sub(r"^\d+[.)]\s+", "", stripped))
            if 15 <= len(content) <= max_len:
                out.append((content, last_heading_was_comm))
        elif in_section and stripped and not _is_bullet_line(line):
            in_section = False
    return out[:25]


def _snippet(text: str, max_chars: int = 200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rsplit(" ", 1)[0] + "..." if max_chars > 3 else text[:max_chars]


def _evidence_entry(page: int, cleaned_line: str) -> Optional[Dict[str, Any]]:
    """Build evidence dict from the cleaned line only (no concatenation with paragraph). Reject if bad fragment."""
    if not cleaned_line or _is_bad_fragment(cleaned_line):
        return None
    cleaned = ct.prepare_evidence_for_display(cleaned_line, max_len=200)
    if cleaned is None:
        cleaned = _clean_line(cleaned_line)
        if _is_bad_fragment(cleaned) or not ct.is_acceptable_evidence(cleaned):
            return None
    return {"page": page, "snippet": cleaned}


MAX_FACTS = 60
MIN_DO_LINES_IF_PRESENT = 10


def _extract_facts_from_pages(
    pages: List[Dict[str, Any]],
    client_name: str,
    doc_id: str,
) -> Tuple[List[Dict[str, Any]], int, int, int, int]:
    """
    Extract facts in priority order: (a) Do/Don't lines, (b) bullets under headings,
    (c) optional driver scores, (d) regex patterns. Evidence = cleaned line only.
    Returns (facts, headings_found, bullets_found, do_lines_found_count, dont_lines_found_count).
    """
    full_text = "\n\n".join(p.get("text", "") for p in pages)
    headings_found = _count_headings(full_text)
    bullets_found = 0
    do_lines_found_count = 0
    dont_lines_found_count = 0
    facts: List[Dict[str, Any]] = []
    seen_labels: set = set()

    # --- (a) Do/Don't lines first (TTI pages) ---
    for page_blob in pages:
        page_num = page_blob["page"]
        text = page_blob["text"] or ""
        if not text.strip():
            continue
        for ftype, label in _extract_do_dont_lines(text):
            if ftype == "trait_do":
                do_lines_found_count += 1
            else:
                dont_lines_found_count += 1
            ev = _evidence_entry(page_num, label)
            if ev and label not in seen_labels:
                seen_labels.add(label)
                facts.append({"type": ftype, "label": label, "evidence": ev})

    # Ensure at least 10 Do lines if we have any (already added above; cap others later)
    do_added = sum(1 for f in facts if f.get("type") == "trait_do")

    # --- (b) Bullets under known headings (short actionable only) ---
    for page_blob in pages:
        if len(facts) >= MAX_FACTS:
            break
        page_num = page_blob["page"]
        text = page_blob["text"] or ""
        if not text.strip():
            continue
        for content, is_comm in _extract_bullets_under_headings(text):
            bullets_found += 1
            label = _clean_line(content)
            if _is_bad_fragment(label) or len(label) < 15:
                continue
            ev = _evidence_entry(page_num, label)
            if not ev or label in seen_labels:
                continue
            ftype = "communication_dont" if any(w in label.lower() for w in ["avoid", "don't", "do not"]) else "communication_do"
            if not is_comm:
                ftype = "risks_dont" if "don't" in label.lower() or "avoid" in label.lower() else "strengths_do"
            seen_labels.add(label)
            facts.append({"type": ftype, "label": label, "evidence": ev})

    # --- (c) Driving Forces: "Intellectual (82)" or "Intellectual 82" -> label=Intellectual, evidence=line ---
    _driver_paren = re.compile(r"(\w+(?:\s+\w+)?)\s*\(\s*(\d{2,3})\s*\)")
    _driver_space = re.compile(r"(\w+(?:\s+\w+)?)\s+(\d{2,3})\b")
    for page_blob in pages:
        if len(facts) >= MAX_FACTS:
            break
        page_num = page_blob["page"]
        text = page_blob["text"] or ""
        for m in _driver_paren.finditer(text):
            driver_name = (m.group(1) or "").strip()
            score_str = m.group(2) if m.lastindex >= 2 else ""
            if not driver_name or len(driver_name) < 2 or len(driver_name) > 40:
                continue
            full_line = _clean_line(m.group(0))
            if _is_bad_fragment(full_line):
                continue
            ev = _evidence_entry(page_num, full_line)
            if not ev:
                continue
            driver_key = "driver:" + driver_name.lower()
            if driver_key in seen_labels:
                continue
            seen_labels.add(driver_key)
            try:
                score = int(score_str) if score_str else None
            except (TypeError, ValueError):
                score = None
            fact = {"type": "driver", "label": driver_name, "evidence": ev}
            if score is not None:
                fact["score"] = score
            facts.append(fact)
        for m in _driver_space.finditer(text):
            driver_name = (m.group(1) or "").strip()
            score_str = m.group(2) if m.lastindex >= 2 else ""
            if not driver_name or len(driver_name) < 2 or len(driver_name) > 40:
                continue
            full_line = _clean_line(m.group(0))
            if _is_bad_fragment(full_line):
                continue
            ev = _evidence_entry(page_num, full_line)
            if not ev:
                continue
            driver_key = "driver:" + driver_name.lower()
            if driver_key in seen_labels:
                continue
            seen_labels.add(driver_key)
            try:
                score = int(score_str) if score_str else None
            except (TypeError, ValueError):
                score = None
            fact = {"type": "driver", "label": driver_name, "evidence": ev}
            if score is not None:
                fact["score"] = score
            facts.append(fact)

    # --- (d) Trait/driver/risk from regex (evidence = phrase only, no concat) ---
    for page_blob in pages:
        if len(facts) >= MAX_FACTS:
            break
        page_num = page_blob["page"]
        text = page_blob["text"] or ""
        for phrase in _find_phrase_matches(text, TRAIT_PATTERNS):
            label = _clean_line(phrase)
            if _is_bad_fragment(label):
                continue
            ev = _evidence_entry(page_num, label)
            if ev and label not in seen_labels:
                seen_labels.add(label)
                facts.append({"type": "trait", "label": label, "evidence": ev})
        for phrase in _find_phrase_matches(text, DRIVER_PATTERNS):
            label = _clean_line(phrase)
            if _is_bad_fragment(label):
                continue
            ev = _evidence_entry(page_num, label)
            if ev and label not in seen_labels:
                seen_labels.add(label)
                facts.append({"type": "driver", "label": label, "evidence": ev})
        for phrase in _find_phrase_matches(text, RISK_PATTERNS):
            label = _clean_line(phrase)
            if _is_bad_fragment(label):
                continue
            ev = _evidence_entry(page_num, label)
            if ev and label not in seen_labels:
                seen_labels.add(label)
                facts.append({"type": "risk", "label": label, "evidence": ev})

    # Do/Don't from bullets when section has communication (TTI without strict Do: line)
    for page_blob in pages:
        if len(facts) >= MAX_FACTS:
            break
        page_num = page_blob["page"]
        text = page_blob["text"] or ""
        lower = text.lower()
        if "communication" in lower or "checklist" in lower:
            for bullet in _extract_bullets(text):
                bullets_found += 1
                label = _clean_line(bullet)
                if _is_bad_fragment(label):
                    continue
                if len(label) < 25 and not re.match(r"^(?:Do|Don\'t)\s*:", label, re.IGNORECASE):
                    continue
                ev = _evidence_entry(page_num, label)
                if not ev or label in seen_labels:
                    continue
                ftype = "communication_dont" if any(w in label.lower() for w in ["avoid", "don't", "do not"]) else "communication_do"
                seen_labels.add(label)
                facts.append({"type": ftype, "label": label, "evidence": ev})

    # Fallback: few bullets if no facts yet
    if not facts and pages:
        for page_blob in pages[:5]:
            for bullet in _extract_bullets(page_blob.get("text") or "")[:10]:
                label = _clean_line(bullet)
                if len(label) < 25 or _is_bad_fragment(label):
                    continue
                bullets_found += 1
                ev = _evidence_entry(page_blob["page"], label)
                if ev and label not in seen_labels:
                    seen_labels.add(label)
                    facts.append({"type": "trait", "label": label, "evidence": ev})

    return facts[:MAX_FACTS], headings_found, bullets_found, do_lines_found_count, dont_lines_found_count


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
            "do_lines_found_count": 0,
            "dont_lines_found_count": 0,
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
            "do_lines_found_count": 0,
            "dont_lines_found_count": 0,
            "facts_count_by_type": {},
            "extraction_message": (
                "This PDF appears to be scanned images; text extraction returned near-zero. "
                "Please upload a text-based PDF."
            ),
        }

    facts, headings_found, bullets_found, do_lines_found_count, dont_lines_found_count = _extract_facts_from_pages(
        pages, client_name, doc_id
    )
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
        "do_lines_found_count": do_lines_found_count,
        "dont_lines_found_count": dont_lines_found_count,
        "facts_count_by_type": facts_count_by_type,
        "extraction_message": None,
    }
