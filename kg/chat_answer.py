"""
Controlled chat answers: deterministic templates from fit context.
Optional local SLM polish (rephrase only; no new facts).
"""
import re
from typing import Dict, Any, Optional

# Intent keywords (lower) -> intent id
INTENT_KEYWORDS = {
    "best_career": ["best career", "which career", "top career", "career fits me", "fits me best", "best fit career"],
    "best_business": ["best business", "which business", "top business", "business fits me", "best fit business"],
    "avoid": ["avoid", "watch out", "what to avoid", "should not", "steer clear", "red flag"],
    "spouse": ["spouse", "partner", "explain to", "share with", "tell my"],
    "30day_plan": ["30-day", "30 day", "action plan", "next steps", "explore", "first steps"],
    "discovery_questions": ["discovery call", "questions to ask", "ask on a call", "next call", "discovery"],
}


def _detect_intent(question: str) -> Optional[str]:
    q = (question or "").lower().strip()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return intent
    return None


def _evidence_lines(ctx: Dict[str, Any], max_quotes: int = 2) -> list:
    """Collect up to max_quotes evidence quotes from top career/business fit."""
    lines = []
    for item in (ctx.get("career_fit") or [])[:1]:
        for e in (item.get("evidence") or [])[:max_quotes]:
            page = e.get("page", "?")
            quote = (e.get("quote") or "").strip()
            if quote:
                lines.append(f'(p.{page}) "{quote}"')
    if len(lines) < max_quotes:
        for item in (ctx.get("business_fit") or [])[:1]:
            for e in (item.get("evidence") or [])[: (max_quotes - len(lines))]:
                page = e.get("page", "?")
                quote = (e.get("quote") or "").strip()
                if quote:
                    lines.append(f'(p.{page}) "{quote}"')
    return lines[:max_quotes]


def _top_signals(ctx: Dict[str, Any], n: int = 3) -> list:
    return (ctx.get("signal_labels") or [])[:n]


def _answer_best_career(ctx: Dict[str, Any]) -> str:
    career = (ctx.get("career_fit") or [])
    best = career[0] if career else {}
    name = best.get("name") or "your top career match"
    why = best.get("why") or "Based on your report signals."
    ev = _evidence_lines(ctx, 2)
    signals = _top_signals(ctx, 3)
    lines = [
        f"**Best career fit:** {name}.",
        f"Why: {why}",
        "**Evidence:** " + ("; ".join(ev) if ev else "Evidence not available; re-run extraction."),
        "**Next step:** Discuss this option with a coach or try one of the recommended actions from the fit card.",
    ]
    return "\n\n".join(lines)


def _answer_best_business(ctx: Dict[str, Any]) -> str:
    biz = (ctx.get("business_fit") or [])
    best = biz[0] if biz else {}
    name = best.get("name") or "your top business match"
    why = best.get("why") or "Based on your report signals."
    ev = _evidence_lines(ctx, 2)
    lines = [
        f"**Best business fit:** {name}.",
        f"Why: {why}",
        "**Evidence:** " + ("; ".join(ev) if ev else "Evidence not available; re-run extraction."),
        "**Next step:** Review watch-outs for this business type and plan one concrete action from the recommendations.",
    ]
    return "\n\n".join(lines)


def _answer_avoid(ctx: Dict[str, Any]) -> str:
    watch_outs = []
    for item in (ctx.get("career_fit") or [])[:2] + (ctx.get("business_fit") or [])[:2]:
        for w in (item.get("watch_outs") or [])[:2]:
            if w:
                watch_outs.append(w)
    if not watch_outs:
        watch_outs = ["Roles with little autonomy.", "Businesses that rely on strict hierarchy or rigid processes."]
    ev = _evidence_lines(ctx, 2)
    lines = [
        "**What to avoid (from your report):**",
        *[f"- {w}" for w in watch_outs[:4]],
        "**Evidence:** " + ("; ".join(ev) if ev else "Evidence not available; re-run extraction."),
        "**Next step:** Use these watch-outs as a checklist when evaluating roles or business opportunities.",
    ]
    return "\n\n".join(lines)


def _answer_spouse(ctx: Dict[str, Any]) -> str:
    career = (ctx.get("career_fit") or [])[:1]
    biz = (ctx.get("business_fit") or [])[:1]
    c_name = career[0].get("name") if career else "your top career fit"
    b_name = biz[0].get("name") if biz else "your top business fit"
    signals = _top_signals(ctx, 3)
    lines = [
        "**How to explain these results:**",
        f"- Your report points to strengths that align with careers like **{c_name}** and businesses like **{b_name}**.",
        f"- Key themes: {', '.join(signals) or 'See the Why section above.'}",
        "- You can say: 'The report suggests I’m a good fit for [X] because [Why]. I’d like to explore that next.'",
        "**Next step:** Share the top 2 fit cards and the 'Why' lines; keep it to 2–3 minutes.",
    ]
    return "\n\n".join(lines)


def _answer_30day_plan(ctx: Dict[str, Any]) -> str:
    career = (ctx.get("career_fit") or [])[:2]
    biz = (ctx.get("business_fit") or [])[:2]
    names = [x.get("name") for x in career + biz if x.get("name")][:2]
    ev = _evidence_lines(ctx, 2)
    lines = [
        "**30-day action plan to explore your top options:**",
        "- Week 1: Write down 2–3 specific aspects of " + (names[0] or "your top fit") + " you want to learn more about.",
        "- Week 2: Find one person (or resource) who works in that space and schedule a short conversation.",
        "- Week 3: Do the same for " + (names[1] if len(names) > 1 else "your second option") + ".",
        "- Week 4: Compare notes and choose one next step (e.g. a course, a trial project, or another call).",
        "**Evidence:** " + ("; ".join(ev) if ev else "Evidence not available; re-run extraction."),
        "**Next step:** Block 30 minutes this week to complete Week 1.",
    ]
    return "\n\n".join(lines)


def _answer_discovery_questions(ctx: Dict[str, Any]) -> str:
    signals = _top_signals(ctx, 3)
    lines = [
        "**Questions to ask on your next discovery call:**",
        "- 'What does a typical day look like for someone in this role/business?'",
        "- 'How much autonomy is there in decision-making?'",
        f"- 'Where do you see someone with strengths in {signals[0] or "these areas"} adding the most value?'" if signals else "- 'Where could someone with my profile add the most value?'",
        "- 'What would you want me to have achieved in the first 90 days?'",
        "**Next step:** Pick 2–3 of these and add one of your own based on your top fit watch-outs.",
    ]
    return "\n\n".join(lines)


_TEMPLATES = {
    "best_career": _answer_best_career,
    "best_business": _answer_best_business,
    "avoid": _answer_avoid,
    "spouse": _answer_spouse,
    "30day_plan": _answer_30day_plan,
    "discovery_questions": _answer_discovery_questions,
}

FALLBACK_MESSAGE = "For now, please choose one of the suggested questions to keep results consistent."


def get_deterministic_answer(question: str, context: Dict[str, Any]) -> str:
    """
    Return a short, structured answer from templates.
    If intent is unknown, return fallback message.
    """
    intent = _detect_intent(question)
    if not intent or intent not in _TEMPLATES:
        return FALLBACK_MESSAGE
    return _TEMPLATES[intent](context)


def polish_with_slm(
    deterministic_answer: str,
    llm_generate=None,
) -> Optional[str]:
    """
    Use local SLM to rephrase the answer in a warmer tone.
    Does NOT add new facts. llm_generate(system_prompt, user_prompt, max_tokens) -> str.
    Returns None if llm_generate is None or fails.
    """
    if not llm_generate or not deterministic_answer:
        return None
    try:
        system = (
            "You rephrase the user's text in a slightly warmer, conversational tone. "
            "Do not add any new facts or recommendations. Keep the same structure (bullets, Evidence, Next step). "
            "Output only the rephrased text, nothing else."
        )
        out = llm_generate(system, deterministic_answer, 400)
        return (out or "").strip() or None
    except Exception:
        return None
