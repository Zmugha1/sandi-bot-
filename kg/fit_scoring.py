"""
Fit scoring: rank career and business archetypes by normalized signals.
Deterministic. Rationale = top 3 contributing signals + evidence + watch-outs.
"""
from pathlib import Path
from typing import Dict, List, Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CAREER_PATH = REPO_ROOT / "data" / "career_archetypes.yaml"
BUSINESS_PATH = REPO_ROOT / "data" / "business_archetypes.yaml"


def _load_archetypes(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return (data or {}).get("archetypes") or []
    except Exception:
        return []


def score_archetypes(
    signals: Dict[str, Dict[str, Any]],
    archetypes: List[Dict[str, Any]],
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Score each archetype by requires (positive) and avoid (penalty).
    signals: { signal_tag: { "score": float, "evidence": [{page, snippet}, ...] } }
    Returns list of { name, description, score, rationale, evidence_used, watch_outs, recommended_actions }.
    """
    scored = []
    for arch in archetypes:
        name = arch.get("name") or ""
        description = arch.get("description") or ""
        requires = arch.get("requires") or {}
        avoid = arch.get("avoid") or {}
        recommended_actions = arch.get("recommended_actions") or []

        pos = 0.0
        neg = 0.0
        contributing = []
        for tag, weight in requires.items():
            w = float(weight) if weight is not None else 1.0
            sig = signals.get(tag) or {}
            s = float(sig.get("score") or 0)
            pos += s * w
            if s > 0:
                contributing.append((tag, s * w, "fit"))

        watch_outs = []
        for tag, weight in avoid.items():
            w = float(weight) if weight is not None else 1.0
            sig = signals.get(tag) or {}
            s = float(sig.get("score") or 0)
            neg += s * w
            if s > 0:
                watch_outs.append(f"{tag} (present in profile)")

        raw_score = pos - neg
        contributing.sort(key=lambda x: -x[1])
        top_signals = [x[0] for x in contributing[:3]]
        rationale = "Strong fit: " + "; ".join(top_signals) if top_signals else "Limited signal match."

        evidence_used = []
        for tag in top_signals[:2]:
            sig = signals.get(tag) or {}
            for ev in (sig.get("evidence") or [])[:2]:
                if ev and (ev.get("page") is not None or ev.get("snippet")):
                    evidence_used.append({
                        "page": ev.get("page"),
                        "snippet": (ev.get("snippet") or "")[:200],
                    })
        if not evidence_used and top_signals:
            sig = signals.get(top_signals[0]) or {}
            for ev in (sig.get("evidence") or [])[:2]:
                if ev:
                    evidence_used.append({"page": ev.get("page"), "snippet": (ev.get("snippet") or "")[:200]})

        scored.append({
            "name": name,
            "description": description,
            "score": round(raw_score, 2),
            "rationale": rationale,
            "evidence_used": evidence_used[:3],
            "watch_outs": watch_outs[:3],
            "recommended_actions": recommended_actions,
        })

    scored.sort(key=lambda x: -x["score"])
    return scored[:top_n]


def get_career_fit(signals: Dict[str, Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    arch = _load_archetypes(CAREER_PATH)
    return score_archetypes(signals, arch, top_n=top_n)


def get_business_fit(signals: Dict[str, Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    arch = _load_archetypes(BUSINESS_PATH)
    return score_archetypes(signals, arch, top_n=top_n)
