"""
Sandi Bot - Synthetic prospect data generator.
100 prospects, 4 personas (Quiet Decider, Overthinker, Burning Bridge, Strategic).
Realistic stall patterns, score correlations, red flags.
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

# Add parent for database import when run as script
import sys
sys.path.insert(0, str(Path(__file__).parent))
import database

COMPARTMENTS = [
    "Discovery",
    "Exploration",
    "Serious Consideration",
    "Decision Prep",
    "Commitment",
]

PERSONAS = [
    "Quiet Decider",
    "Overthinker",
    "Burning Bridge",
    "Strategic",
]

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
]

DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "company.com", "business.org"]


def _score_for_persona(persona: str, compartment: str) -> tuple:
    """
    Return (identity, commitment, financial, execution) 1-5 scores
    with persona-appropriate correlations and stall patterns.
    """
    base = random.randint(2, 4)
    # Quiet Decider: high execution, decisive, often in later compartments
    if persona == "Quiet Decider":
        execution = min(5, base + random.randint(0, 2))
        commitment = min(5, base + random.randint(0, 1))
        identity = min(5, base + random.randint(-1, 1))
        financial = min(5, base + random.randint(-1, 1))
    # Overthinker: lower commitment/execution, gets stuck in Exploration
    elif persona == "Overthinker":
        execution = max(1, base + random.randint(-2, 0))
        commitment = max(1, base + random.randint(-1, 0))
        identity = min(5, base + random.randint(0, 1))
        financial = max(1, base + random.randint(-1, 1))
    # Burning Bridge: high commitment/identity, may rush
    elif persona == "Burning Bridge":
        commitment = min(5, base + random.randint(0, 2))
        identity = min(5, base + random.randint(0, 1))
        execution = min(5, base + random.randint(-1, 1))
        financial = min(5, base + random.randint(-1, 1))
    # Strategic: balanced, all dimensions matter
    else:
        identity = min(5, base + random.randint(-1, 1))
        commitment = min(5, base + random.randint(-1, 1))
        financial = min(5, base + random.randint(-1, 1))
        execution = min(5, base + random.randint(-1, 1))

    def clamp(x):
        return max(1, min(5, x))

    return (
        clamp(identity),
        clamp(commitment),
        clamp(financial),
        clamp(execution),
    )


def _compartment_days_for_persona(persona: str, compartment: str) -> int:
    """Overthinkers stick in Exploration 30+ days; others vary."""
    if persona == "Overthinker" and compartment == "Exploration":
        return random.randint(30, 75)
    if compartment == "Commitment":
        return random.randint(1, 14)
    return random.randint(3, 45)


def _red_flags(identity: int, commitment: int, financial: int, execution: int, persona: str) -> list:
    """Generate realistic red flags from scores and persona."""
    flags = []
    if financial <= 2:
        flags.append("avoiding_money_talk")
    if execution <= 2:
        flags.append("no_follow_through")
    if commitment <= 2 and persona == "Overthinker":
        flags.append("indecisive")
    if identity <= 2:
        flags.append("blame_external")
    return flags


def _conversion_probability(scores: tuple, compartment: str, persona: str, compartment_days: int) -> float:
    """Simple conversion probability 0-1 from scores, stage, and stall."""
    i, c, f, e = scores
    avg = (i + c + f + e) / 4.0
    stage_bonus = {"Discovery": 0.1, "Exploration": 0.2, "Serious Consideration": 0.4, "Decision Prep": 0.7, "Commitment": 0.9}.get(compartment, 0.2)
    stall_penalty = 0
    if persona == "Overthinker" and compartment_days > 30:
        stall_penalty = 0.15
    p = (avg / 5.0) * 0.5 + stage_bonus * 0.5 - stall_penalty
    return round(max(0.0, min(1.0, p + random.uniform(-0.05, 0.05))), 3)


def _last_interaction(days_ago_min: int, days_ago_max: int) -> str:
    d = datetime.utcnow() - timedelta(days=random.randint(days_ago_min, days_ago_max))
    return d.strftime("%Y-%m-%d")


def generate_one_prospect(prospect_id: str, persona: str, compartment: str) -> dict:
    """Generate a single prospect record."""
    idx = int(prospect_id.replace("P", "")) if prospect_id.startswith("P") else 0
    first = FIRST_NAMES[idx % len(FIRST_NAMES)]
    last = LAST_NAMES[(idx // len(FIRST_NAMES)) % len(LAST_NAMES)]
    name = f"{first} {last}"
    email = f"{first.lower()}.{last.lower()}@{random.choice(DOMAINS)}"

    identity, commitment, financial, execution = _score_for_persona(persona, compartment)
    compartment_days = _compartment_days_for_persona(persona, compartment)
    red_flags = _red_flags(identity, commitment, financial, execution, persona)
    conv_prob = _conversion_probability((identity, commitment, financial, execution), compartment, persona, compartment_days)
    last_int = _last_interaction(1, 60)

    return {
        "prospect_id": prospect_id,
        "name": name,
        "email": email,
        "persona": persona,
        "compartment": compartment,
        "compartment_days": compartment_days,
        "identity_score": identity,
        "commitment_score": commitment,
        "financial_score": financial,
        "execution_score": execution,
        "conversion_probability": conv_prob,
        "last_interaction_date": last_int,
        "red_flags": red_flags,
        "context_json": {
            "last_topic": random.choice(["pricing", "timeline", "objections", "next_steps", "case_study"]),
            "next_action": random.choice(["call", "email", "demo", "proposal", "follow_up"]),
        },
    }


def generate_all_prospects(count: int = 100) -> list:
    """Generate count prospects: 25 of each persona, compartments distributed."""
    records = []
    per_persona = count // 4
    pid = 1
    for persona in PERSONAS:
        for _ in range(per_persona):
            compartment = random.choices(
                COMPARTMENTS,
                weights=[15, 25, 25, 20, 15],
                k=1
            )[0]
            prospect_id = f"P{pid:03d}"
            records.append(generate_one_prospect(prospect_id, persona, compartment))
            pid += 1
    random.shuffle(records)
    return records


def load_synthetic_into_db(records: list) -> int:
    """Insert all records into DB. Creates DB if needed. Returns number inserted."""
    database.init_db()
    n = 0
    for r in records:
        try:
            database.insert_prospect(r)
            n += 1
        except Exception:
            # Skip duplicates
            pass
    return n


def ensure_synthetic_data():
    """If DB has no prospects, generate and load 100. Return list of prospects."""
    database.init_db()
    existing = database.get_all_prospects()
    if len(existing) >= 100:
        return existing
    records = generate_all_prospects(100)
    load_synthetic_into_db(records)
    return database.get_all_prospects()


if __name__ == "__main__":
    ensure_synthetic_data()
    prospects = database.get_all_prospects()
    print(f"Loaded {len(prospects)} prospects. Sample: {prospects[0]}")
