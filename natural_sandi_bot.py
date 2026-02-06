"""
Sandi Bot - Chat: SimpleSandiBot (no API key) + call planning template + optional OpenAI fallback.
"""
from typing import Optional, List, Dict, Any

# Cluster (persona) strategy one-liners for call plan
CLUSTER_STRATEGY = {
    "Quiet Decider": "They decide internally; don't over-pitch. One clear ask and a deadline.",
    "Overthinker": "Reduce overwhelm with one homework item and a short follow-up call.",
    "Burning Bridge": "They're ready to move; match their urgency with a clear next step.",
    "Strategic": "Respect their process; provide options and a recommendation with dates.",
}

COMPARTMENTS_BAND = [
    "Discovery", "Exploration", "Serious Consideration", "Decision Prep", "Commitment",
]


def _build_call_plan_template(prospect: dict) -> str:
    """Detailed call plan using algorithm outputs: cluster, compartment band, scores, action, next steps."""
    import sandi_bot
    name = prospect.get("name", "this prospect")
    pid = prospect.get("prospect_id", "")
    persona = prospect.get("persona", "Strategic")
    comp = prospect.get("compartment", "Discovery")
    days = prospect.get("compartment_days", 0)
    i = prospect.get("identity_score", 0)
    c = prospect.get("commitment_score", 0)
    f = prospect.get("financial_score", 0)
    e = prospect.get("execution_score", 0)
    conv = prospect.get("conversion_probability", 0)
    red = prospect.get("red_flags") or []
    strategy_line = CLUSTER_STRATEGY.get(persona, CLUSTER_STRATEGY["Strategic"])
    action, confidence, reason = sandi_bot.get_recommendation(prospect)
    tactics = sandi_bot.get_tactics(persona, action)
    _, advance_reason = sandi_bot.recommend_advancement(prospect)
    comp_index = COMPARTMENTS_BAND.index(comp) if comp in COMPARTMENTS_BAND else 0
    band_display = " → ".join(
        f"**{c}**" if idx == comp_index else c
        for idx, c in enumerate(COMPARTMENTS_BAND)
    )
    conv_pct = int(round(conv * 100))
    conf_pct = int(round(confidence * 100))
    red_text = ", ".join(red) if red else "None"
    script_lines = "\n".join(f"- {t}" for t in (tactics[:3] if tactics else ["—"]))

    return f"""**📞 Call plan: {name}** (ID: {pid})

---
**Cluster (persona)**  
**{persona}**  
Strategy: {strategy_line}

---
**Compartment band** (where they are now)  
{band_display}  
• Current stage: **{comp}** (Stage {comp_index + 1} of 5)  
• Days in this stage: **{days}**

---
**Readiness scores** (1–5)  
| Dimension   | Score | Note |
|-------------|-------|------|
| Identity    | {i} | Ownership vs blame |
| Commitment  | {c} | Ability to decide |
| Financial   | {f} | Comfort with money |
| Execution   | {e} | Follow-through |

---
**Conversion probability:** {conv_pct}%  
**Red flags:** {red_text}

---
**Recommended action:** **{action}** (confidence: {conf_pct}%)  
{reason}

---
**What to do next / scripts**  
{script_lines}

---
**Compartment advancement**  
{advance_reason}
"""


class SimpleSandiBot:
    """Rule-based Sandi - no OpenAI key needed."""

    def generate_response(self, question: str, prospect: Optional[dict] = None, history=None) -> str:
        prospect = prospect or {}
        name = prospect.get("name", "them")
        days = prospect.get("days_in_compartment", prospect.get("compartment_days", 0))

        q = (question or "").lower()
        # Call planning: detailed template with cluster, compartment band, strategy, next steps
        if ("plan" in q and "call" in q) or ("next call" in q) or ("help me plan" in q):
            if prospect.get("prospect_id") or prospect.get("name"):
                return _build_call_plan_template(prospect)
            return "Load a customer first: enter a **Customer #** and **Name** in the sidebar and click **Start ▶**. Then ask again for your call plan."
        if "push" in q:
            if days > 21:
                return f"I'd actually PAUSE with {name}. {days} days is too long - let them breathe for 2 weeks."
            else:
                return f"Yes, push {name}! They're ready. Schedule the decision call this week."
        elif "homework" in q:
            return f"Give {name} ONE specific thing with a deadline. Like: 'Send me your top 3 concerns by Friday.'"
        elif "pause" in q:
            return f"Step back for 2 weeks. If {name} doesn't reach out, they weren't going to convert anyway."
        else:
            return f"I'd keep nurturing {name}. They're warming up but need more time. What specifically are you unsure about?"


# Use this for chat (no API key required)
sandi_bot_simple = SimpleSandiBot()


def simple_chat_response(question: str, prospect: Optional[dict] = None, history=None) -> str:
    """Use SimpleSandiBot for chat. No OpenAI key needed."""
    if not (question or "").strip():
        return "What would you like to know?"
    return sandi_bot_simple.generate_response(question, prospect, history)


# --- Optional OpenAI (kept for reference; not used when SimpleSandiBot is active)
def _client(api_key: str):
    import openai
    return openai.OpenAI(api_key=api_key)


def _build_system_prompt(prospect: Optional[dict]) -> str:
    """One-time system prompt describing Sandi's role and current prospect context."""
    base = """You are Sandi, a warm and experienced sales coach. You help salespeople decide whether to PUSH (call today, ask for the decision), NURTURE (continue engagement, assign homework), or PAUSE (step back 2 weeks) with each prospect. You speak in plain English, like a trusted colleague. You give specific, actionable advice and sometimes suggest exact phrases or emails. You never sound robotic or template-like.

Framework you use:
- 5 compartments (stages): Discovery → Exploration → Serious Consideration → Decision Prep → Commitment.
- 4 personas: Quiet Decider (decides quietly, high execution), Overthinker (gets stuck, needs homework), Burning Bridge (urgent, high commitment), Strategic (balanced, process-oriented).
- 4 readiness scores (1-5 each): Identity, Commitment, Financial, Execution. Low Financial = avoid pushing on money; low Execution = they don't follow through.
- Actions: PUSH = green, call now with a script; NURTURE = yellow, keep engaging; PAUSE = red, step back."""
    if prospect:
        name = prospect.get("name", "this prospect")
        pid = prospect.get("prospect_id", "")
        persona = prospect.get("persona", "Strategic")
        comp = prospect.get("compartment", "Discovery")
        days = prospect.get("compartment_days", 0)
        i = prospect.get("identity_score", 0)
        c = prospect.get("commitment_score", 0)
        f = prospect.get("financial_score", 0)
        e = prospect.get("execution_score", 0)
        conv = prospect.get("conversion_probability", 0)
        red = prospect.get("red_flags") or []
        base += f"""

Current prospect: {name} (ID: {pid})
- Persona: {persona}
- Compartment: {comp} ({days} days in this stage)
- Scores: Identity {i}, Commitment {c}, Financial {f}, Execution {e}
- Conversion probability: {conv:.0%}
- Red flags: {", ".join(red) if red else "None"}"""
    else:
        base += "\n\nNo specific prospect is loaded. If the user asks for a recommendation, ask them to enter a Customer # and Name and start a strategy session first."
    return base


def natural_response(
    user_message: str,
    api_key: str,
    prospect: Optional[dict] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Get a warm, natural reply from Sandi using GPT-3.5-turbo.
    chat_history: list of {"role": "user"|"assistant", "content": "..."}.
    """
    if not api_key or not user_message.strip():
        return "I didn't catch that. What would you like to know?"

    system = _build_system_prompt(prospect)
    messages = [{"role": "system", "content": system}]

    # Last 10 exchanges to keep context manageable
    history = (chat_history or [])[-20:]
    for h in history:
        role = h.get("role")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message.strip()})

    try:
        client = _client(api_key)
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        choice = resp.choices[0] if resp.choices else None
        if choice and getattr(choice, "message", None):
            return (choice.message.content or "").strip()
        return "I couldn't generate a response. Try asking again."
    except Exception as e:
        err = str(e).lower()
        if "invalid" in err or "api" in err or "key" in err or "auth" in err:
            return "That API key doesn't work. Check it at platform.openai.com and paste a new one in the sidebar."
        if "rate" in err or "limit" in err:
            return "I'm hitting rate limits. Wait a minute and try again."
        return f"Something went wrong: {e}. Try again or use the app without an API key for template responses."
