"""
Deterministic templates: call plan, client summary, follow-up email.
No LLM required. Used for "Plan My Next Call", "Summarize This Client", "Draft Follow-up Email".
"""
from typing import Dict, List, Any

# ---- Call plan: 20-min agenda + 5 questions ----
CALL_PLAN_AGENDA = [
    ("0–2 min", "Check-in and set outcome for the call"),
    ("2–6 min", "Review progress or blockers since last touchpoint"),
    ("6–12 min", "Main topic: decision, next step, or exploration"),
    ("12–18 min", "Clarify next actions and ownership"),
    ("18–20 min", "Confirm next contact and close"),
]

def _top_signal_labels(signals: Dict[str, Dict[str, Any]], n: int = 5) -> List[str]:
    items = [(tag, data.get("score") or 0) for tag, data in (signals or {}).items()]
    items.sort(key=lambda x: -x[1])
    return [x[0] for x in items[:n]]


def render_call_plan(
    signals: Dict[str, Dict[str, Any]],
    stage: str = "",
    profile: str = "",
) -> str:
    """One-page 20-min call plan: agenda + 5 questions derived from top signals."""
    lines = ["## Call plan (20 min)", ""]
    lines.append("**Agenda**")
    for slot, desc in CALL_PLAN_AGENDA:
        lines.append(f"- **{slot}** — {desc}")
    lines.append("")
    top = _top_signal_labels(signals, 5)
    lines.append("**Suggested questions (use 2–3 based on fit)**")
    q_map = [
        ("People-oriented", "What would make this a win for you and your team?"),
        ("Big-picture thinker", "Where do you see this fitting in your priorities over the next 6 months?"),
        ("Autonomy-seeking", "What would you want to own vs. have support on?"),
        ("Needs clear decisions (yes/no closure)", "What’s the one decision we can nail down today?"),
        ("Competitive / challenge-driven", "What’s the biggest challenge we should tackle first?"),
        ("Security / stability-seeking", "What would need to be in place for you to feel comfortable moving forward?"),
        ("Creative / flexible", "What would an ideal outcome look like if we had no constraints?"),
        ("Relationship-focused", "Who else should we loop in so this sticks?"),
    ]
    used = set()
    for tag in top:
        for t, q in q_map:
            if t in tag or tag in t:
                if q not in used:
                    lines.append(f"- {q}")
                    used.add(q)
                    break
    if len([l for l in lines if l.strip().startswith("-") and "?" in l]) < 3:
        for t, q in q_map:
            if q not in used:
                lines.append(f"- {q}")
                used.add(q)
                if len(used) >= 5:
                    break
    lines.append("")
    if stage or profile:
        lines.append(f"*Context: stage={stage or '—'}, profile={profile or '—'}*")
    return "\n".join(lines)


def render_client_summary(signals: Dict[str, Dict[str, Any]]) -> str:
    """8–10 bullet client summary from top signals and evidence."""
    lines = ["## Client summary", ""]
    items = [(tag, data.get("score") or 0, (data.get("evidence") or [])[:2]) for tag, data in (signals or {}).items()]
    items.sort(key=lambda x: -x[1])
    for tag, score, ev_list in items[:10]:
        lines.append(f"- **{tag}** (strength: {score:.0f})")
        for ev in ev_list[:1]:
            snip = (ev.get("snippet") or "").strip()[:120]
            if snip:
                lines.append(f"  - p.{ev.get('page', '?')}: {snip}...")
    return "\n".join(lines) if len(lines) > 2 else "Not enough signals to summarize. Add more insights from the report."


def render_followup_email_template(
    signals: Dict[str, Dict[str, Any]],
    outcome_text: str = "",
    client_name: str = "there",
) -> str:
    """Deterministic follow-up email draft. Optional outcome_text (e.g. from call)."""
    top = _top_signal_labels(signals, 3)
    lines = [
        f"Hi {client_name},",
        "",
        "Following up on our conversation.",
    ]
    if outcome_text:
        lines.append("")
        lines.append(outcome_text.strip())
    lines.append("")
    if "Needs clear decisions (yes/no closure)" in top or top:
        lines.append("Next step: I’ll send a short summary and one clear ask by [date]. If anything shifts on your side, just reply to this thread.")
    else:
        lines.append("Next step: I’ll follow up with [specific item] by [date]. Feel free to reply with any questions.")
    lines.append("")
    lines.append("Best,")
    lines.append("[Your name]")
    lines.append("")
    lines.append("*Draft generated from stored client insights; review before sending.*")
    return "\n".join(lines)
