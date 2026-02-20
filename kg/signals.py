"""
Signal normalization: map extracted facts (traits/drivers/risks) to stable signal tags.
Deterministic, no LLM. Evidence is cleaned and limited to 2 high-quality snippets per signal.
"""
from typing import Dict, List, Any

from . import clean_text as ct

# Stable signal tags (canonical set)
SIGNAL_TAGS = [
    "People-oriented",
    "Big-picture thinker",
    "Autonomy-seeking",
    "Persuasive / influence",
    "Competitive / challenge-driven",
    "Low tolerance for rigid rules",
    "Prefers risk-taking environments",
    "Avoid strict diplomacy environments",
    "Avoid strict adherence to standards",
    "Needs clear decisions (yes/no closure)",
    "Detail-oriented",
    "Security / stability-seeking",
    "Creative / flexible",
    "Relationship-focused",
    "Impact / helping-driven",
]

# Map: phrase substring (lower) -> list of signal tags. First match wins per fact.
PHRASE_TO_SIGNALS: List[tuple] = [
    # People-oriented
    ("people", "People-oriented"),
    ("team", "People-oriented"),
    ("relationship", "People-oriented"),
    ("communicat", "People-oriented"),
    ("collaborat", "People-oriented"),
    ("connect", "People-oriented"),
    ("helping others", "People-oriented"),
    ("recognition", "People-oriented"),
    ("impact", "People-oriented"),
    # Big-picture
    ("big picture", "Big-picture thinker"),
    ("vision", "Big-picture thinker"),
    ("strategic", "Big-picture thinker"),
    ("concept", "Big-picture thinker"),
    ("overview", "Big-picture thinker"),
    # Autonomy
    ("autonomy", "Autonomy-seeking"),
    ("independence", "Autonomy-seeking"),
    ("self-directed", "Autonomy-seeking"),
    ("control", "Autonomy-seeking"),
    ("own pace", "Autonomy-seeking"),
    ("freedom", "Autonomy-seeking"),
    # Persuasive / influence
    ("persuad", "Persuasive / influence"),
    ("influence", "Persuasive / influence"),
    ("convinc", "Persuasive / influence"),
    ("lead", "Persuasive / influence"),
    ("negotiat", "Persuasive / influence"),
    # Competitive
    ("competit", "Competitive / challenge-driven"),
    ("challenge", "Competitive / challenge-driven"),
    ("win", "Competitive / challenge-driven"),
    ("achievement", "Competitive / challenge-driven"),
    ("goal-oriented", "Competitive / challenge-driven"),
    # Low tolerance rigid rules
    ("rigid", "Low tolerance for rigid rules"),
    ("rules", "Low tolerance for rigid rules"),
    ("bureaucrac", "Low tolerance for rigid rules"),
    ("flexibility", "Low tolerance for rigid rules"),
    ("flexible", "Low tolerance for rigid rules"),
    ("structure", "Low tolerance for rigid rules"),
    # Risk-taking
    ("risk", "Prefers risk-taking environments"),
    ("entrepreneur", "Prefers risk-taking environments"),
    ("innov", "Prefers risk-taking environments"),
    ("variety", "Prefers risk-taking environments"),
    ("change", "Prefers risk-taking environments"),
    # Avoid strict diplomacy
    ("avoid conflict", "Avoid strict diplomacy environments"),
    ("conflict", "Avoid strict diplomacy environments"),
    ("diplomac", "Avoid strict diplomacy environments"),
    ("politic", "Avoid strict diplomacy environments"),
    ("confrontation", "Avoid strict diplomacy environments"),
    # Avoid strict standards
    ("avoid strict", "Avoid strict adherence to standards"),
    ("standards", "Avoid strict adherence to standards"),
    ("compliance", "Avoid strict adherence to standards"),
    ("procedure", "Avoid strict adherence to standards"),
    # Clear decisions
    ("decision", "Needs clear decisions (yes/no closure)"),
    ("closure", "Needs clear decisions (yes/no closure)"),
    ("clear outcome", "Needs clear decisions (yes/no closure)"),
    ("yes or no", "Needs clear decisions (yes/no closure)"),
    ("deadline", "Needs clear decisions (yes/no closure)"),
    # Detail-oriented
    ("detail", "Detail-oriented"),
    ("analytical", "Detail-oriented"),
    ("data", "Detail-oriented"),
    ("accuracy", "Detail-oriented"),
    ("precision", "Detail-oriented"),
    # Security / stability
    ("security", "Security / stability-seeking"),
    ("stability", "Security / stability-seeking"),
    ("certainty", "Security / stability-seeking"),
    ("predictab", "Security / stability-seeking"),
    ("guarantee", "Security / stability-seeking"),
    # Creative / flexible
    ("creative", "Creative / flexible"),
    ("innovative", "Creative / flexible"),
    ("adapt", "Creative / flexible"),
    # Relationship-focused (alias)
    ("relationship-focused", "Relationship-focused"),
    ("people-focused", "Relationship-focused"),
    # Impact / helping
    ("helping", "Impact / helping-driven"),
    ("impact-driven", "Impact / helping-driven"),
    ("purpose", "Impact / helping-driven"),
    # TTI Driving Forces (clean labels -> signals)
    ("intellectual", "Big-picture thinker"),
    ("receptive", "People-oriented"),
    ("aesthetic", "Creative / flexible"),
    ("economic", "Competitive / challenge-driven"),
    ("individualistic", "Autonomy-seeking"),
    ("altruistic", "Impact / helping-driven"),
    ("regulatory", "Security / stability-seeking"),
    ("theoretical", "Big-picture thinker"),
    ("utilitarian", "Detail-oriented"),
]


def _match_signals(label: str, fact_type: str) -> List[str]:
    """Return list of signal tags that match this fact label (and optionally type). Deterministic."""
    if not label or not isinstance(label, str):
        return []
    lower = label.lower().strip()
    out = []
    seen = set()
    for phrase, tag in PHRASE_TO_SIGNALS:
        if phrase in lower and tag not in seen:
            out.append(tag)
            seen.add(tag)
    return out


MAX_EVIDENCE_PER_SIGNAL = 2


def normalize_facts_to_signals(facts: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Map extracted facts to stable signal tags.
    Returns: { signal_tag: { "score": float, "evidence": [ {"page": N, "snippet": "..."}, ... ] } }
    Score = number of facts contributing to this signal (1.0 per fact).
    Evidence: only acceptable snippets (clean_text); max 2 per signal for demo-ready display.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for fact in facts or []:
        if not fact or not isinstance(fact, dict):
            continue
        label = fact.get("label") or ""
        evidence = fact.get("evidence") or {}
        if isinstance(evidence, list):
            ev_list = evidence[:2]
            page = ev_list[0].get("page") if ev_list else None
            snippet = ev_list[0].get("snippet", "") if ev_list else ""
        else:
            page = evidence.get("page")
            snippet = (evidence.get("snippet") or "").strip()
        cleaned = ct.prepare_evidence_for_display(snippet, max_len=200)
        if cleaned is None and snippet and ct.is_acceptable_evidence(ct.clean_evidence_snippet(snippet, max_len=200)):
            cleaned = ct.clean_evidence_snippet(snippet, max_len=200)
        ev_entry = {"page": page, "snippet": cleaned} if cleaned else None
        tags = _match_signals(label, fact.get("type") or "")
        if not tags:
            tags = ["Relationship-focused"]
        for tag in tags:
            if tag not in result:
                result[tag] = {"score": 0.0, "evidence": []}
            result[tag]["score"] = result[tag]["score"] + 1.0
            if ev_entry and len(result[tag]["evidence"]) < MAX_EVIDENCE_PER_SIGNAL:
                result[tag]["evidence"].append(ev_entry)
    return result
