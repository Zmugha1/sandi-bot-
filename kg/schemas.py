"""
Schemas for Ollama vision extraction: validate and convert JSON into extract_pdf fact format.
"""
from typing import List, Dict, Any

# --- Ollama extraction response (vision model output) ---


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def ollama_response_to_facts(
    data: Dict[str, Any],
    default_page: int = 1,
) -> List[Dict[str, Any]]:
    """
    Convert Ollama JSON response to list of facts in extract_pdf format.
    Each fact: { "type": str, "label": str, "evidence": { "page": int, "snippet": str } }.
    """
    facts: List[Dict[str, Any]] = []
    quotes_by_page: Dict[int, List[str]] = {}
    for eq in data.get("evidence_quotes") or []:
        page = _get(eq, "page", default_page)
        quote = _get(eq, "quote", "")
        if quote and isinstance(quote, str):
            quotes_by_page.setdefault(int(page) if page is not None else default_page, []).append(quote[:200])

    def evidence_for_page(p: int) -> Dict[str, Any]:
        snip = ""
        if p in quotes_by_page and quotes_by_page[p]:
            snip = quotes_by_page[p][0]
        return {"page": p, "snippet": snip or f"(from page {p})"}

    page = default_page
    for label in (data.get("traits_do") or []):
        if label and isinstance(label, str) and len(label.strip()) >= 3:
            lbl = label.strip()
            if not lbl.lower().startswith("do:"):
                lbl = f"Do: {lbl}"
            facts.append({"type": "trait_do", "label": lbl, "evidence": evidence_for_page(page)})
    for label in (data.get("traits_dont") or []):
        if label and isinstance(label, str) and len(label.strip()) >= 3:
            lbl = label.strip()
            if not lbl.lower().startswith("don't") and not lbl.lower().startswith("dont"):
                lbl = f"Don't: {lbl}"
            facts.append({"type": "trait_dont", "label": lbl, "evidence": evidence_for_page(page)})
    for dr in (data.get("drivers") or []):
        lab = _get(dr, "label", "")
        if lab and isinstance(lab, str) and len(lab.strip()) >= 2:
            facts.append({"type": "driver", "label": lab.strip(), "evidence": evidence_for_page(page)})
    for label in (data.get("risks") or []):
        if label and isinstance(label, str) and len(label.strip()) >= 3:
            facts.append({"type": "risk", "label": label.strip(), "evidence": evidence_for_page(page)})

    return facts


def validate_ollama_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and validate Ollama response dict; return safe dict for ollama_response_to_facts."""
    if not data or not isinstance(data, dict):
        return {}
    out: Dict[str, Any] = {
        "traits_do": list(data.get("traits_do") or []) if isinstance(data.get("traits_do"), list) else [],
        "traits_dont": list(data.get("traits_dont") or []) if isinstance(data.get("traits_dont"), list) else [],
        "drivers": list(data.get("drivers") or []) if isinstance(data.get("drivers"), list) else [],
        "risks": list(data.get("risks") or []) if isinstance(data.get("risks"), list) else [],
        "evidence_quotes": list(data.get("evidence_quotes") or []) if isinstance(data.get("evidence_quotes"), list) else [],
    }
    return out
