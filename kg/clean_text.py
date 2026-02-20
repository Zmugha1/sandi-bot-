"""
Clean and filter evidence snippets for demo-ready display.
- Remove section boilerplate, truncation artifacts, normalize whitespace.
- Reject fragments: lowercase start, boilerplate, meaningless short phrases.
"""
import re
from typing import Optional

# Boilerplate patterns to strip (case-insensitive)
SECTION_LEAD_IN = re.compile(
    r"^(?:Behavioral\s+Characteristics\s+)?Based\s+on\s+[\w\s]+\'s\s+responses[.,]?\s*",
    re.IGNORECASE,
)
BASED_ON_RESPONSES = re.compile(r"Based\s+on\s+[\w\s]+\'s\s+responses", re.IGNORECASE)
MASK_SOME_OF = re.compile(r"mask\s+some\s+of", re.IGNORECASE)

MIN_READABLE_LEN = 25
MIN_COMPLETE_SENTENCE_FOR_MASK = 80
MAX_SNIPPET_LEN = 200


def normalize_whitespace(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_section_lead_in(s: str) -> str:
    """Remove leading 'Behavioral Characteristics Based on X's responses' etc."""
    if not s:
        return ""
    s = normalize_whitespace(s)
    s = SECTION_LEAD_IN.sub("", s).strip()
    return s


def ensure_ending(s: str) -> str:
    """Ensure snippet ends with . ! ? or is a clear Do:/Don't: phrase."""
    if not s or len(s) < 3:
        return s
    s = s.strip()
    if re.match(r"^(?:Do|Don\'t|DON\'T)\s*:\s*.+", s, re.IGNORECASE):
        return s
    if s[-1] in ".!?":
        return s
    if len(s) >= MAX_SNIPPET_LEN or s.endswith("..."):
        return s
    return s + "."


def clean_evidence_snippet(s: str, max_len: int = MAX_SNIPPET_LEN) -> str:
    """
    Clean a raw snippet: strip boilerplate, normalize whitespace, fix ending.
    Does not truncate mid-word; may return shorter string.
    """
    if not s or not isinstance(s, str):
        return ""
    s = strip_section_lead_in(s)
    s = normalize_whitespace(s)
    if len(s) > max_len:
        s = s[: max_len - 3].rsplit(" ", 1)[0] + "..." if max_len > 3 else s[:max_len]
    s = ensure_ending(s)
    return s


def is_acceptable_evidence(snippet: str) -> bool:
    """
    Return False for meaningless or fragment evidence.
    - Reject if starts with lowercase (likely fragment).
    - Reject if contains 'Based on X's responses' boilerplate.
    - Reject if contains 'mask some of' unless full snippet is >= 80 chars (complete sentence).
    - Reject if < 25 chars and not a Do:/Don't: phrase.
    """
    if not snippet or not isinstance(snippet, str):
        return False
    s = normalize_whitespace(snippet).strip()
    if not s:
        return False

    is_do_dont = bool(re.match(r"^(?:Do|Don\'t|DON\'T)\s*:\s*.+", s, re.IGNORECASE))
    if len(s) < MIN_READABLE_LEN and not is_do_dont:
        return False
    if s[0].islower():
        return False
    if BASED_ON_RESPONSES.search(s):
        return False
    if MASK_SOME_OF.search(s) and len(s) < MIN_COMPLETE_SENTENCE_FOR_MASK:
        return False
    return True


def prepare_evidence_for_display(snippet: str, max_len: int = MAX_SNIPPET_LEN) -> Optional[str]:
    """
    Clean and validate; return None if not acceptable, else cleaned string.
    Use this before storing or showing evidence.
    """
    cleaned = clean_evidence_snippet(snippet, max_len=max_len)
    if not is_acceptable_evidence(cleaned):
        return None
    return cleaned
