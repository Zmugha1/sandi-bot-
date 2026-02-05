"""
Sandi Bot - Natural LLM conversation using OpenAI GPT-3.5-turbo.
Warm, human-like coaching (no robotic templates).
"""
from typing import Optional, List, Dict, Any

# Lazy import so app runs without openai if not used
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
