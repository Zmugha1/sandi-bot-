"""
Sandi Bot - Chat strategy engine.
Intent detection (push/pause, homework, financial, etc.), response generators,
word-for-word scripts, confidence calculation, tactics by persona and action.
"""
import re
from typing import Optional, List, Dict, Any, Tuple

# --- Tactics database: persona -> action -> list of tactics (scripts / tips)
TACTICS_DB = {
    "Quiet Decider": {
        "PUSH": [
            "Call today. Say: 'I have one slot left this week for a quick decision call. Can we lock it in for 15 minutes?'",
            "Email: 'Based on our last conversation, you're ready. Here are two times that work for me. Which do you prefer?'",
            "Script: 'What's the one thing that would need to be true for you to move forward this week?'",
        ],
        "NURTURE": [
            "Send one case study that matches their industry. Follow up in 3 days.",
            "Ask: 'What would help you feel 100% ready to decide?' Then assign that as homework.",
            "Script: 'I'll send you a short checklist. When you've gone through it, we'll talk for 10 minutes.'",
        ],
        "PAUSE": [
            "Step back 2 weeks. Send a single value email (no ask) in 10 days.",
            "Script: 'I don't want to push. When the timing is right, reach out. I'll be here.'",
        ],
    },
    "Overthinker": {
        "PUSH": [
            "Call and say: 'I'm going to give you one question to sit with. What's the cost of not deciding in the next 30 days?'",
            "Script: 'Let's make this simple. What's your biggest fear about moving forward? One sentence.'",
            "Offer a 10-minute 'no pressure' call to answer one objection.",
        ],
        "NURTURE": [
            "Homework: 'Write down the top 3 reasons you're considering this. Send them to me before our next call.'",
            "Script: 'What would need to happen for you to feel 80% confident? Let's name it.'",
            "Send a 2-minute video addressing the objection they repeat most.",
        ],
        "PAUSE": [
            "Pause 2 weeks. Then one short email: 'Still on your mind? Here's a 2-min read that might help.'",
            "Script: 'I can tell you need space. When you're ready to talk through the block, I'm here.'",
        ],
    },
    "Burning Bridge": {
        "PUSH": [
            "Call today. Script: 'You said you need this sorted by [date]. Let's get it done. I have 20 minutes now.'",
            "Send calendar link: 'Here's my availability. Pick a time in the next 48 hours.'",
            "Script: 'What's the one thing standing between you and signing? Let's remove it now.'",
        ],
        "NURTURE": [
            "Confirm next step in writing: 'So we're agreed: [X] by [date]. I'll hold you to it.'",
            "Script: 'You're committed. What's the very next action you'll take?'",
            "Send a short recap email with one clear CTA and deadline.",
        ],
        "PAUSE": [
            "Only if they've gone silent. One email: 'Checking in. Still want to move forward? No pressure.'",
            "Script: 'If now isn't the right time, tell me. We can pause and pick up when you're ready.'",
        ],
    },
    "Strategic": {
        "PUSH": [
            "Call: 'You've done the homework. Let's make the decision. I have openings tomorrow.'",
            "Script: 'What information do you still need? I'll get it to you today so we can close this week.'",
            "Email: 'Summary of what we've agreed. Next step: 15-min decision call. Here are 3 times.'",
        ],
        "NURTURE": [
            "Assign one piece of homework: ROI calculation or comparison matrix. Due in 5 days.",
            "Script: 'What's your decision process? Who else is involved? Let's map it.'",
            "Send a one-page proposal with clear options A/B/C and a recommendation.",
        ],
        "PAUSE": [
            "Pause 2 weeks. Send one relevant article or tool. No ask.",
            "Script: 'When your timeline is clearer, we can pick up. I'll send one resource in the meantime.'",
        ],
    },
}

# Default persona if missing
DEFAULT_PERSONA = "Strategic"

# Compartment thresholds: (min count of scores >= 3, min count >= 4) for advancement
COMPARTMENT_RULES = {
    "Discovery": (2, 0),
    "Exploration": (3, 0),
    "Serious Consideration": (3, 1),
    "Decision Prep": (4, 2),
    "Commitment": (4, 3),
}


def _scores(prospect: dict) -> Tuple[int, int, int, int]:
    i = prospect.get("identity_score", 3)
    c = prospect.get("commitment_score", 3)
    f = prospect.get("financial_score", 3)
    e = prospect.get("execution_score", 3)
    return (i, c, f, e)


def _recommend_action(prospect: dict) -> Tuple[str, float, str]:
    """
    Recommend PUSH, NURTURE, or PAUSE with confidence 0-1 and short reason.
    """
    if not prospect:
        return "NURTURE", 0.5, "No prospect data."
    i, c, f, e = _scores(prospect)
    comp = prospect.get("compartment", "Discovery")
    days = prospect.get("compartment_days", 0)
    persona = prospect.get("persona", DEFAULT_PERSONA)
    conv = prospect.get("conversion_probability", 0.5)

    # Red flags push toward PAUSE
    red = prospect.get("red_flags") or []
    if "avoiding_money_talk" in red and f <= 2:
        return "PAUSE", 0.75, "Financial comfort is low; they're avoiding money talk. Step back and nurture."
    if "no_follow_through" in red and e <= 2:
        return "PAUSE", 0.7, "Execution is weak; they haven't followed through. Pause and re-engage later."

    # High scores + late stage -> PUSH
    if comp in ("Decision Prep", "Commitment") and (i + c + f + e) >= 16 and conv >= 0.6:
        return "PUSH", min(0.95, 0.6 + conv * 0.35), "Scores and stage support moving to close. Call today."
    if comp == "Serious Consideration" and conv >= 0.55 and e >= 4:
        return "PUSH", 0.65, "Strong execution and readiness. Good time to ask for the decision."

    # Overthinker stuck in Exploration 30+ days -> NURTURE with homework
    if persona == "Overthinker" and comp == "Exploration" and days >= 30:
        return "NURTURE", 0.7, "Overthinker stuck in Exploration. Assign one clear homework; don't push yet."
    if persona == "Overthinker" and (c <= 2 or e <= 2):
        return "NURTURE", 0.65, "Commitment or execution is low. Nurture with one question or homework."

    # Early stage, low scores -> PAUSE
    if comp == "Discovery" and (i + c + f + e) <= 10:
        return "PAUSE", 0.6, "Early stage and low readiness. Step back 2 weeks, then one value touch."
    if conv < 0.35:
        return "PAUSE", 0.65, "Conversion probability is low. Pause and re-engage in 2 weeks."

    # Default
    return "NURTURE", 0.6, "Continue engagement with one clear next step or homework."


def detect_intent(message: str) -> str:
    """Classify user message into intent category."""
    msg = (message or "").strip().lower()
    if not msg:
        return "unknown"
    if re.search(r"\b(push|pause|call|nurture|what should i do|recommend|action)\b", msg):
        return "push_pause"
    if re.search(r"\b(homework|assign|give them|task|prep)\b", msg):
        return "homework"
    if re.search(r"\b(money|financial|price|cost|pay|investment|afford)\b", msg):
        return "financial"
    if re.search(r"\b(script|say|word for word|exact|phrase)\b", msg):
        return "script"
    if re.search(r"\b(persona|type|overthinker|quiet|strategic|burning)\b", msg):
        return "persona"
    if re.search(r"\b(compartment|stage|where are they)\b", msg):
        return "compartment"
    if re.search(r"\b(hello|hi|hey|start)\b", msg):
        return "greeting"
    return "general"


def get_recommendation(prospect: dict) -> Tuple[str, float, str]:
    """Public: (action, confidence, reason) for a prospect."""
    return _recommend_action(prospect)


def get_tactics(persona: str, action: str) -> List[str]:
    """Return list of tactic scripts for persona + action."""
    p = TACTICS_DB.get(persona) or TACTICS_DB.get(DEFAULT_PERSONA)
    tactics = (p or {}).get(action, [])
    return tactics if tactics else ["Continue the conversation and ask for one clear next step."]


def recommend_advancement(prospect: dict) -> Tuple[bool, str]:
    """Should we recommend advancing to next compartment? (can_advance, reason)."""
    i, c, f, e = _scores(prospect)
    comp = prospect.get("compartment", "Discovery")
    comps = ["Discovery", "Exploration", "Serious Consideration", "Decision Prep", "Commitment"]
    idx = comps.index(comp) if comp in comps else 0
    if idx >= len(comps) - 1:
        return False, "Already in Commitment."
    min_3, min_4 = COMPARTMENT_RULES.get(comp, (3, 0))
    scores = [i, c, f, e]
    count_ge3 = sum(1 for s in scores if s >= 3)
    count_ge4 = sum(1 for s in scores if s >= 4)
    if count_ge3 >= min_3 and count_ge4 >= min_4:
        next_comp = comps[idx + 1]
        return True, f"Scores support moving to {next_comp}. Suggest advancing in next call."
    return False, f"Need {min_3} scores ≥3 and {min_4} ≥4 to advance from {comp}. Current: {count_ge3} ≥3, {count_ge4} ≥4."


def generate_response(
    intent: str,
    prospect: Optional[dict],
    prospect_id: Optional[str],
    prospect_name: Optional[str],
) -> Tuple[str, Optional[str], Optional[float], Optional[str], Optional[List[str]]]:
    """
    Generate (response_text, action, confidence, script_snippet, tactics_list).
    """
    action = None
    confidence = None
    script_snippet = None
    tactics_list = None
    name = prospect_name or (prospect.get("name") if prospect else "") or prospect_id or "this prospect"

    if intent == "greeting":
        if prospect_id and prospect:
            return (
                f"Hi! I've loaded **{name}**. Ask me: *Should I push or pause?* or *What homework should I give them?* or *What should I say on the call?*",
                None, None, None, None,
            )
        return (
            "Hi! Enter a **Customer #** and **Name** above and click **Start Strategy Session**, then I'll load their profile and we can plan your next move.",
            None, None, None, None,
        )

    if intent != "push_pause" and intent != "homework" and intent != "financial" and intent != "script" and intent != "general":
        if not prospect:
            return (
                f"Please start a strategy session with a customer (Customer # and Name) so I can give you a specific answer.",
                None, None, None, None,
            )
        # persona / compartment: short answer
        if intent == "persona":
            p = (prospect or {}).get("persona", DEFAULT_PERSONA)
            return f"**{name}** is a **{p}**. I'll tailor scripts and tactics to this type.", None, None, None, None
        if intent == "compartment":
            comp = (prospect or {}).get("compartment", "Discovery")
            days = (prospect or {}).get("compartment_days", 0)
            return f"**{name}** is in **{comp}** ({days} days). Use this to decide push vs nurture.", None, None, None, None
        # fallback
        return (
            f"For **{name}**, ask me: *Should I push or pause?* or *What homework?* or *What script should I use?*",
            None, None, None, None,
        )

    if not prospect:
        return (
            "Please enter a **Customer #** and **Name** and click **Start Strategy Session** so I can see their scores and give you a recommendation.",
            None, None, None, None,
        )

    # Push/Pause + script + homework + financial all use recommendation
    action, confidence, reason = _recommend_action(prospect)
    persona = prospect.get("persona", DEFAULT_PERSONA)
    tactics_list = get_tactics(persona, action)
    script_snippet = tactics_list[0] if tactics_list else None

    # Build response by intent
    if intent == "push_pause":
        conf_pct = int(round((confidence or 0) * 100))
        text = f"**Recommendation: {action}** (confidence: {conf_pct}%)\n\n{reason}\n\n"
        text += "**Suggested script (word-for-word):**\n" + (script_snippet or "N/A")
        return text, action, confidence, script_snippet, tactics_list

    if intent == "homework":
        # Prefer a NURTURE-style tactic that sounds like homework
        homework_tactics = [t for t in tactics_list if "homework" in t.lower() or "write" in t.lower() or "send" in t.lower() or "checklist" in t.lower()]
        assign = (homework_tactics or tactics_list)[0]
        text = f"**Action: {action}**\n\n**Homework to assign:**\n{assign}"
        return text, action, confidence, assign, tactics_list

    if intent == "financial":
        if "avoiding_money_talk" in (prospect.get("red_flags") or []):
            script_snippet = "I'm not here to sell you today. I'd like to understand what would need to be true for the numbers to work for you. What's your biggest concern about the investment?"
        else:
            script_snippet = "Can we spend 2 minutes on the numbers? What's your budget or range so I can show you the best option?"
        text = f"**Financial angle:** Their financial score is **{prospect.get('financial_score', 0)}**. Use this script:\n\n\"{script_snippet}\""
        return text, action, confidence, script_snippet, tactics_list

    if intent == "script":
        text = f"**Word-for-word script for {name}** ({action}):\n\n{script_snippet}"
        if tactics_list and len(tactics_list) > 1:
            text += "\n\n**Other options:**\n" + "\n".join(f"- {t}" for t in tactics_list[1:3])
        return text, action, confidence, script_snippet, tactics_list

    # general: still give recommendation
    conf_pct = int(round((confidence or 0) * 100))
    text = f"For **{name}**: I recommend **{action}** ({conf_pct}% confidence). {reason}\n\n**Script:** {script_snippet}"
    return text, action, confidence, script_snippet, tactics_list
