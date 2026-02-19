"""
SandyBot Strategy Advisor: decision-support using only client knowledge graph context.
Never invents facts. If evidence missing, says "Not enough evidence in graph."
Output: Recommendation, Why (traits/drivers/risks), Signals Still Missing, Suggested Next Step.
Deterministic; no LLM.
"""
import re
from typing import Dict, Any, List, Optional


def _context_to_lists(context: Dict[str, Any]) -> tuple:
    """Return (traits, drivers, risks) as lists of {label, evidence}."""
    traits = []
    drivers = []
    risks = []
    for item in (context.get("traits") or []):
        traits.append({"label": (item.get("label") or "").strip(), "evidence": item.get("evidence") or {}})
    for item in (context.get("drivers") or []):
        drivers.append({"label": (item.get("label") or "").strip(), "evidence": item.get("evidence") or {}})
    for item in (context.get("risks") or []):
        risks.append({"label": (item.get("label") or "").strip(), "evidence": item.get("evidence") or {}})
    return traits, drivers, risks


def _has_evidence(traits: List, drivers: List, risks: List) -> bool:
    return bool(traits or drivers or risks)


def _question_intent(question: str) -> str:
    """Classify intent: approach, risk, need, next_step, money, decision, general."""
    q = (question or "").lower().strip()
    if not q:
        return "general"
    if re.search(r"\b(how\s+should i\s+approach|approach\s+them|best\s+way\s+to)\b", q):
        return "approach"
    if re.search(r"\b(risk|watch\s+out|avoid|pitfall)\b", q):
        return "risk"
    if re.search(r"\b(need|want|motivat|driver|value)\b", q):
        return "need"
    if re.search(r"\b(next\s+step|what\s+to\s+do|suggested\s+action)\b", q):
        return "next_step"
    if re.search(r"\b(money|financial|investment|price)\b", q):
        return "money"
    if re.search(r"\b(decision|decide|commit)\b", q):
        return "decision"
    return "general"


def _cite(labels: List[str], kind: str) -> str:
    if not labels:
        return ""
    return f"{kind}(s): " + "; ".join(labels[:5]) + "."


def advise(context: Dict[str, Any], user_question: str) -> Dict[str, Any]:
    """
    Input:
      context: { "client_name": str, "traits": [...], "drivers": [...], "risks": [...] }
               each item has "label" and optional "evidence": { "page", "snippet" }
      user_question: str

    Output:
      {
        "recommendation": str,
        "why": str,
        "signals_still_missing": List[str],
        "suggested_next_step": str
      }
    Never invents. If no evidence in context, recommendation = "Not enough evidence in graph."
    """
    traits, drivers, risks = _context_to_lists(context)
    client_name = (context.get("client_name") or "This client").strip()

    if not _has_evidence(traits, drivers, risks):
        return {
            "recommendation": "Not enough evidence in graph.",
            "why": "",
            "signals_still_missing": ["Upload a personality report or build insights for this client."],
            "suggested_next_step": "Upload a PDF and click Build Insights, then ask again.",
        }

    trait_labels = [t["label"] for t in traits if t["label"]]
    driver_labels = [d["label"] for d in drivers if d["label"]]
    risk_labels = [r["label"] for r in risks if r["label"]]

    intent = _question_intent(user_question)
    recommendation = ""
    why_parts = []
    signals_missing = []
    next_step = ""

    # Build recommendation and why from context only
    if intent == "approach":
        if driver_labels:
            recommendation = f"Lead with what motivates them: frame the conversation around {driver_labels[0]}."
            why_parts.append(_cite(driver_labels[:2], "Driver"))
        if risk_labels:
            if recommendation:
                recommendation += f" Avoid triggering: {risk_labels[0]}."
            else:
                recommendation = f"Avoid triggering: {risk_labels[0]}. Adjust tone and pace accordingly."
            why_parts.append(_cite(risk_labels[:2], "Risk"))
        if trait_labels and not recommendation:
            recommendation = f"Match their style: {trait_labels[0]}. Use that to shape your ask."
            why_parts.append(_cite(trait_labels[:2], "Trait"))
        if not recommendation:
            recommendation = "Use the traits and drivers above to tailor your opening; keep the ask clear and time-bound."
            why_parts.append(_cite(trait_labels + driver_labels, "Trait/Driver"))

    elif intent == "risk":
        if risk_labels:
            recommendation = f"Primary risk in graph: {risk_labels[0]}. Plan to mitigate (e.g. reframe, small step, or name it gently)."
            why_parts.append(_cite(risk_labels, "Risk"))
        else:
            recommendation = "No explicit risks in graph. Stay alert to hesitation or avoidance in the conversation."
            why_parts.append(_cite(trait_labels[:2], "Trait"))
        signals_missing = ["Specific situations that trigger the risk."] if risk_labels else ["What they tend to avoid or fear."]

    elif intent == "need":
        if driver_labels:
            recommendation = f"Address their drivers: {', '.join(driver_labels[:3])}. Tie your recommendation to how it serves these."
            why_parts.append(_cite(driver_labels, "Driver"))
        else:
            recommendation = "No drivers in graph. Ask in the next call: 'What would make this a clear yes for you?'"
            why_parts.append("No drivers extracted yet.")
        signals_missing = ["How strongly each driver ranks."] if driver_labels else ["What they value most."]

    elif intent == "next_step":
        if risk_labels and any("decision" in r.lower() or "overthink" in r.lower() or "avoid" in r.lower() for r in risk_labels):
            recommendation = "Give one clear next step and one deadline. Avoid open-ended options."
            why_parts.append(_cite(risk_labels, "Risk"))
        elif driver_labels:
            recommendation = f"Frame the next step as something they own: e.g. 'You choose the date' or 'You set the outcome.'"
            why_parts.append(_cite(driver_labels[:2], "Driver"))
        else:
            recommendation = "Propose one concrete action and one short-term checkpoint (e.g. 48 hours)."
            why_parts.append(_cite(trait_labels[:2], "Trait"))
        next_step = "In the next call: state the one action, the deadline, and ask: 'What would need to be true for you to do this by then?'"

    elif intent == "money":
        money_risks = [r for r in risk_labels if "money" in r.lower() or "financial" in r.lower()]
        if money_risks:
            recommendation = "Introduce money early and calmly; confirm comfort level before numbers. Use their language."
            why_parts.append(_cite(money_risks, "Risk"))
        else:
            recommendation = "No money-specific risk in graph. Still: name the investment and the return in their terms (drivers/traits)."
            why_parts.append(_cite(driver_labels + trait_labels[:1], "Driver/Trait"))
        signals_missing = ["Their past experience with money conversations."] if not money_risks else []

    elif intent == "decision":
        decision_risks = [r for r in risk_labels if "decision" in r.lower() or "overthink" in r.lower() or "paralysis" in r.lower()]
        if decision_risks:
            recommendation = "Limit options to 2 and set a decision deadline. Offer: 'A or B by [date].'"
            why_parts.append(_cite(decision_risks, "Risk"))
        else:
            recommendation = "Be explicit: 'I need a yes or no by X.' Then pause. Use traits to choose tone."
            why_parts.append(_cite(trait_labels[:2], "Trait"))
        next_step = next_step or "Ask: 'What would need to be true for you to decide by [date]?'"

    else:
        # general
        recommendation = "Use traits to match style, drivers to motivate, and risks to avoid pitfalls. Keep one clear ask and one deadline."
        why_parts.append(_cite(trait_labels[:2], "Trait"))
        why_parts.append(_cite(driver_labels[:2], "Driver"))
        if risk_labels:
            why_parts.append(_cite(risk_labels[:2], "Risk"))
        signals_missing = ["Their timeline."] if not any("time" in r.lower() or "deadline" in r.lower() for r in risk_labels + trait_labels) else []

    why = " ".join(why_parts) if why_parts else "Based on the traits, drivers, and risks in the graph."
    if not next_step:
        next_step = "In the next call: one clear ask, one deadline, and one check for blockers."

    return {
        "recommendation": recommendation or "Not enough evidence in graph.",
        "why": why,
        "signals_still_missing": signals_missing,
        "suggested_next_step": next_step,
    }
