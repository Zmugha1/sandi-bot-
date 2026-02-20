"""
Chat context pack: only normalized signals + top fit results + evidence.
No raw traits or PDF text. Used for controlled, demo-safe Q&A.
"""
from typing import Dict, List, Any


def build_chat_context(
    signals: Dict[str, Dict[str, Any]],
    career_fit: List[Dict[str, Any]],
    business_fit: List[Dict[str, Any]],
    client_name: str = "",
    business_type: str = "",
) -> Dict[str, Any]:
    """
    Build a minimal context dict for the chat answer engine.
    Uses only: signal labels, top 5 career/business fit (name, why, watch_outs, evidence_used).
    """
    signal_labels = list(signals.keys()) if signals else []

    def _summarize_fit(items: List[Dict[str, Any]], max_items: int = 5) -> List[Dict[str, Any]]:
        out = []
        for i, x in enumerate((items or [])[:max_items]):
            ev_quotes = []
            for e in (x.get("evidence_used") or [])[:2]:
                page = e.get("page", "?")
                snip = (e.get("snippet") or "").strip()
                if snip:
                    ev_quotes.append({"page": page, "quote": snip})
            out.append({
                "rank": i + 1,
                "name": x.get("name") or "",
                "description": (x.get("description") or "").strip(),
                "why": (x.get("rationale") or "").strip(),
                "watch_outs": (x.get("watch_outs") or [])[:2],
                "evidence": ev_quotes,
                "recommended_actions": (x.get("recommended_actions") or [])[:2],
            })
        return out

    return {
        "client_name": client_name or "",
        "business_type": (business_type or "").strip(),
        "signal_labels": signal_labels,
        "career_fit": _summarize_fit(career_fit),
        "business_fit": _summarize_fit(business_fit),
    }
