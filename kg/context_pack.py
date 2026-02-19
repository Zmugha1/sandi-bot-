"""
Build a deterministic context pack from the Knowledge Graph for SLM grounding.
Caps: max 12 facts total, max 2 evidence snippets per fact, max 240 chars per snippet.
"""
from typing import Dict, Any, List, Optional
import networkx as nx

from . import build_graph as bg
from . import ontology as o
from . import recommendations as rec
from . import similarity as sim

MAX_FACTS_TOTAL = 12
MAX_EVIDENCE_PER_FACT = 2
MAX_SNIPPET_LEN = 240


def _truncate(s: str, max_len: int) -> str:
    if not s or len(s) <= max_len:
        return s or ""
    return s[: max_len - 3].rsplit(" ", 1)[0] + "..." if max_len > 3 else s[:max_len]


def _fact_entry(label: str, evidence_list: List[Dict]) -> Dict[str, Any]:
    """One fact with at most MAX_EVIDENCE_PER_FACT snippets, each truncated."""
    snippets = []
    for ev in (evidence_list or [])[:MAX_EVIDENCE_PER_FACT]:
        if isinstance(ev, dict):
            sn = ev.get("snippet")
            if sn:
                snippets.append({"doc_id": ev.get("doc_id"), "page": ev.get("page"), "snippet": _truncate(str(sn), MAX_SNIPPET_LEN)})
        else:
            snippets.append({"snippet": _truncate(str(ev), MAX_SNIPPET_LEN)})
    return {"label": (label or "")[:200], "evidence": snippets}


def build_context_pack(G: nx.MultiDiGraph, client_name: str) -> Dict[str, Any]:
    """
    Returns a dict for SLM prompts. Uses ONLY graph and deterministic modules.
    Caps total facts so context stays bounded.
    """
    cid = o.client_id(client_name)
    pack = {
        "client_name": client_name or "",
        "current_compartment": "",
        "profile": "",
        "traits": [],
        "drivers": [],
        "risks": [],
        "recommendations": [],
        "similar_clients": [],
    }
    if not G.has_node(cid):
        return pack

    tdr = bg.get_client_traits_drivers_risks(G, client_name)
    def _ev_list(ev):
        return [ev] if ev and isinstance(ev, dict) else (ev if isinstance(ev, list) else [])

    traits = []
    for t in (tdr.get("traits") or []):
        traits.append(_fact_entry(t.get("label") or "", _ev_list(t.get("evidence"))))
    drivers = []
    for d in (tdr.get("drivers") or []):
        drivers.append(_fact_entry(d.get("label") or "", _ev_list(d.get("evidence"))))
    risks = []
    for r in (tdr.get("risks") or []):
        risks.append(_fact_entry(r.get("label") or "", _ev_list(r.get("evidence"))))

    recs = rec.get_recommendations(
        [{"label": t.get("label"), "evidence": t.get("evidence")} for t in (tdr.get("traits") or [])],
        [{"label": d.get("label"), "evidence": d.get("evidence")} for d in (tdr.get("drivers") or [])],
        [{"label": r.get("label"), "evidence": r.get("evidence")} for r in (tdr.get("risks") or [])],
        max_n=5,
    )
    recommendations = []
    for r in recs:
        ev = r.get("evidence") or {}
        recommendations.append({
            "action": (r.get("action") or "")[:200],
            "why": (r.get("why") or "")[:200],
            "evidence": [{"page": ev.get("page"), "snippet": _truncate(str(ev.get("snippet") or ""), MAX_SNIPPET_LEN)}],
        })

    similar = sim.get_similar_clients(
        tdr.get("traits") or [],
        tdr.get("drivers") or [],
        tdr.get("risks") or [],
        top_n=3,
    )
    similar_clients = []
    for sclient, score, overlap in similar:
        similar_clients.append({
            "name": sclient.get("name") or "",
            "business_type": sclient.get("business_type") or "",
            "why_similar": ", ".join(overlap[:5]) if overlap else "similar profile",
        })

    # Cap total facts (traits + drivers + risks as "facts")
    all_facts = traits + drivers + risks
    if len(all_facts) > MAX_FACTS_TOTAL:
        traits = traits[: min(len(traits), MAX_FACTS_TOTAL)]
        remaining = MAX_FACTS_TOTAL - len(traits)
        drivers = drivers[: min(len(drivers), remaining)]
        remaining -= len(drivers)
        risks = risks[: max(0, min(len(risks), remaining))]
    pack["traits"] = traits
    pack["drivers"] = drivers
    pack["risks"] = risks
    pack["recommendations"] = recommendations
    pack["similar_clients"] = similar_clients
    return pack


def count_facts_in_pack(pack: Dict[str, Any]) -> int:
    """Number of facts (traits + drivers + risks) for guardrail."""
    return len(pack.get("traits") or []) + len(pack.get("drivers") or []) + len(pack.get("risks") or [])
