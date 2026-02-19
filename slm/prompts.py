"""
Fixed prompt templates for Strategy Tools. SLM must use ONLY the context pack;
do not invent facts. If info missing, say "Not enough evidence in graph."
"""
from typing import Dict, Any

SYSTEM_INSTRUCT = (
    "You are a writing assistant for a coach. Use ONLY the context pack provided. "
    "Do not invent facts or add information not in the context. "
    "If the context is missing required information, respond with exactly: Not enough evidence in graph."
)

def _format_context(pack: Dict[str, Any]) -> str:
    parts = []
    if pack.get("client_name"):
        parts.append(f"Client: {pack['client_name']}")
    if pack.get("profile"):
        parts.append(f"Profile: {pack['profile']}")
    for label, key in [("Traits", "traits"), ("Drivers", "drivers"), ("Risks", "risks")]:
        items = pack.get(key) or []
        if items:
            lines = []
            for it in items:
                lab = it.get("label") or ""
                evs = it.get("evidence") or []
                snips = [e.get("snippet", "")[:200] for e in evs if e]
                lines.append(f"- {lab}" + (f" (evidence: {'; '.join(snips)})" if snips else ""))
            parts.append(f"{label}:\n" + "\n".join(lines))
    recs = pack.get("recommendations") or []
    if recs:
        lines = []
        for r in recs:
            action = r.get("action") or ""
            why = r.get("why") or ""
            lines.append(f"- {action} (why: {why})")
        parts.append("Recommendations:\n" + "\n".join(lines))
    similar = pack.get("similar_clients") or []
    if similar:
        lines = [f"- {s.get('name')} ({s.get('business_type')}): {s.get('why_similar', '')}" for s in similar]
        parts.append("Similar clients:\n" + "\n".join(lines))
    return "\n\n".join(parts) if parts else "(No context)"

# ---- Email Follow-Up ----
def system_prompt_email() -> str:
    return SYSTEM_INSTRUCT + " Write a short, professional follow-up email draft based only on the context."

def user_prompt_email(pack: Dict[str, Any], call_outcome: str = "") -> str:
    ctx = _format_context(pack)
    outcome = f" Call outcome to reference (if any): {call_outcome}." if call_outcome else ""
    return f"Context pack:\n{ctx}\n{outcome}\n\nWrite a brief follow-up email (2-4 sentences) using only the above. No invented facts."

# ---- Strategy Summary ----
def system_prompt_summary() -> str:
    return SYSTEM_INSTRUCT + " Write a bullet-point strategy summary for the coach using only the context."

def user_prompt_summary(pack: Dict[str, Any]) -> str:
    ctx = _format_context(pack)
    return f"Context pack:\n{ctx}\n\nWrite a short bullet-point strategy summary (traits, drivers, risks, key recommendations). Use only the above. No invented facts."

# ---- Call Agenda ----
def system_prompt_agenda() -> str:
    return SYSTEM_INSTRUCT + " Write a timeboxed call agenda using only the context."

def user_prompt_agenda(pack: Dict[str, Any], duration_min: int = 20) -> str:
    ctx = _format_context(pack)
    return f"Context pack:\n{ctx}\n\nWrite a {duration_min}-minute call agenda with timeboxes (e.g. 0-5 min: X, 5-10 min: Y). Use only the above. No invented facts."

# ---- Tool type -> (system_builder, user_builder, max_tokens) ----
def get_prompt_builders(tool_type: str):
    if tool_type == "Email Follow-Up":
        return (system_prompt_email, lambda p, **kw: user_prompt_email(p, call_outcome=kw.get("call_outcome", "")), 250)
    if tool_type == "Strategy Summary":
        return (system_prompt_summary, lambda p, **kw: user_prompt_summary(p), 350)
    if tool_type == "Call Agenda":
        return (system_prompt_agenda, lambda p, **kw: user_prompt_agenda(p, duration_min=kw.get("duration_min", 20)), 250)
    return (system_prompt_summary, lambda p, **kw: user_prompt_summary(p), 350)
