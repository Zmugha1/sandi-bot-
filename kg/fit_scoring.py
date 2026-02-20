"""
Fit scoring: rank career and business archetypes by normalized signals.
Deterministic. Evidence max 2, demo-safe (cleaned, quality-scored). Rationale = Why: labels. Watch-outs actionable.
"""
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple

from . import clean_text as ct

REPO_ROOT = Path(__file__).resolve().parent.parent
CAREER_PATH = REPO_ROOT / "data" / "career_archetypes.yaml"
BUSINESS_PATH = REPO_ROOT / "data" / "business_archetypes.yaml"

# Boilerplate / junk to strip or reject
_BOILERPLATE_PATTERNS = [
    re.compile(r"Behavioral\s+Characteristics\s+Based\s+on\b", re.IGNORECASE),
    re.compile(r"Based\s+on\s+[\w\s]+\'s\s+responses[.,]?\s*", re.IGNORECASE),
    re.compile(r"the\s+report\s+has\s+selected\s+general\s+statements[.,]?\s*", re.IGNORECASE),
]
_JUNK_PHRASES = ("mask some of", "working as", "based on", "selected general statements")
_MAX_EVIDENCE_BULLETS = 2
_MAX_WATCH_OUTS = 2


def _clean_snippet(s: str) -> str:
    """Normalize whitespace, remove boilerplate fragments, strip leading/trailing punctuation."""
    if not s or not isinstance(s, str):
        return ""
    out = re.sub(r"\s+", " ", s).strip()
    for pat in _BOILERPLATE_PATTERNS:
        out = pat.sub("", out).strip()
    out = out.strip(".,;:!?\-–— \t")
    return out


def _is_bad_evidence(s: str) -> bool:
    """Return True if snippet should not be shown (junk, fragment, or too short)."""
    if not s or not isinstance(s, str):
        return True
    s = s.strip()
    if len(s) < 18:
        return True
    is_do_dont = bool(re.match(r"^(?:Do|Don\'t|DON\'T|Dont)\s*:\s*", s, re.IGNORECASE))
    if s[0].islower() and not is_do_dont:
        return True
    lower = s.lower()
    for junk in _JUNK_PHRASES:
        if junk in lower:
            return True
    if not re.search(r"\b[a-zA-Z]+\b", s):
        return True
    if s.endswith("...") and s.count("...") >= 2:
        return True
    if len(s) > 20 and s[-1] not in ".!?" and not is_do_dont:
        if not re.search(r"\b(?:Do|Don\'t)\s*:\s*", s, re.IGNORECASE):
            return True
    return False


def _evidence_quality(s: str) -> int:
    """Higher = better. Prefer Do:/Don't:, concise, 20–120 chars, ends with punctuation."""
    if not s:
        return 0
    s = s.strip()
    score = 0
    if re.match(r"^(?:Do|Don\'t|DON\'T|Dont)\s*:\s*", s, re.IGNORECASE):
        score += 50
    if 20 <= len(s) <= 120:
        score += 20
    elif 18 <= len(s) <= 150:
        score += 10
    if s[-1] in ".!?":
        score += 10
    if re.search(r"\b(?:people[- ]oriented|big thinker|direct|focused|results?)\b", s, re.IGNORECASE):
        score += 5
    if "..." not in s or s.count("...") < 2:
        score += 5
    return score


def _signal_to_label(tag: str) -> str:
    """Convert machine tag to human label: snake_case -> Title Case."""
    if not tag:
        return ""
    return str(tag).replace("_", " ").strip().title()


def _pick_evidence(
    signals: Dict[str, Dict[str, Any]],
    top_signals: List[str],
    max_bullets: int = _MAX_EVIDENCE_BULLETS,
) -> List[Dict[str, Any]]:
    """
    From top contributing tags, collect evidence; clean, filter, score.
    Return up to max_bullets unique snippets, sorted by quality desc then page asc.
    """
    candidates: List[Tuple[int, int, str]] = []
    for tag in top_signals:
        sig = signals.get(tag) or {}
        for ev in sig.get("evidence") or []:
            if not ev:
                continue
            raw = (ev.get("snippet") or "").strip()
            if not raw:
                continue
            cleaned = _clean_snippet(raw)
            if not cleaned or _is_bad_evidence(cleaned):
                continue
            if not ct.is_acceptable_evidence(cleaned):
                continue
            page = ev.get("page") or 0
            try:
                page = int(page)
            except (TypeError, ValueError):
                page = 0
            quality = _evidence_quality(cleaned)
            snippet_show = cleaned[:200] if len(cleaned) > 200 else cleaned
            candidates.append((quality, page, snippet_show))

    candidates.sort(key=lambda x: (-x[0], x[1]))
    seen: set = set()
    out = []
    for _q, page, snippet in candidates:
        if len(out) >= max_bullets:
            break
        key = snippet.strip().lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append({"page": page, "snippet": snippet})
    return out


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

        watch_out_tags = []
        for tag, weight in avoid.items():
            w = float(weight) if weight is not None else 1.0
            sig = signals.get(tag) or {}
            s = float(sig.get("score") or 0)
            neg += s * w
            if s > 0:
                watch_out_tags.append(tag)

        raw_score = pos - neg
        contributing.sort(key=lambda x: -x[1])
        top_signals = [x[0] for x in contributing[:3]]
        labels = [_signal_to_label(t) for t in top_signals if t]
        rationale = "Why: " + "; ".join(labels) if labels else "Limited signal match."

        evidence_used = _pick_evidence(signals, top_signals, max_bullets=_MAX_EVIDENCE_BULLETS)

        watch_outs = []
        for tag in watch_out_tags[: _MAX_WATCH_OUTS]:
            label = _signal_to_label(tag)
            watch_outs.append(f"Watch-out: {label} — adjust approach")

        scored.append({
            "name": name,
            "description": description,
            "score": round(raw_score, 2),
            "rationale": rationale,
            "evidence_used": evidence_used,
            "watch_outs": watch_outs,
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
