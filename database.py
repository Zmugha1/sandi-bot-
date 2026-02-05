"""
Sandi Bot - SQLite database layer.
Tables: prospects, interactions, chat_history, feedback.
CRUD operations and JSON context storage.
"""
import sqlite3
import json
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

DB_PATH = Path(__file__).parent / "sandi_bot.db"


def get_connection():
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they do not exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            persona TEXT,
            compartment TEXT,
            compartment_days INTEGER,
            identity_score INTEGER,
            commitment_score INTEGER,
            financial_score INTEGER,
            execution_score INTEGER,
            conversion_probability REAL,
            last_interaction_date TEXT,
            red_flags TEXT,
            context_json TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT NOT NULL,
            interaction_type TEXT,
            notes TEXT,
            outcome TEXT,
            created_at TEXT,
            FOREIGN KEY (prospect_id) REFERENCES prospects(prospect_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            context_snapshot TEXT,
            created_at TEXT,
            FOREIGN KEY (prospect_id) REFERENCES prospects(prospect_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT,
            recommendation_type TEXT,
            user_rating INTEGER NOT NULL,
            message_id INTEGER,
            created_at TEXT,
            FOREIGN KEY (prospect_id) REFERENCES prospects(prospect_id),
            FOREIGN KEY (message_id) REFERENCES chat_history(id)
        )
    """)

    conn.commit()
    conn.close()


# --- Prospects CRUD ---

def insert_prospect(record: dict) -> Optional[int]:
    """Insert a single prospect. Returns row id or None."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat() + "Z"
    record.setdefault("created_at", now)
    record.setdefault("updated_at", now)
    context_json = json.dumps(record.get("context_json")) if isinstance(record.get("context_json"), dict) else record.get("context_json")
    red_flags = json.dumps(record.get("red_flags")) if isinstance(record.get("red_flags"), list) else record.get("red_flags")
    cur.execute("""
        INSERT INTO prospects (
            prospect_id, name, email, persona, compartment, compartment_days,
            identity_score, commitment_score, financial_score, execution_score,
            conversion_probability, last_interaction_date, red_flags, context_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.get("prospect_id"), record.get("name"), record.get("email"),
        record.get("persona"), record.get("compartment"), record.get("compartment_days"),
        record.get("identity_score"), record.get("commitment_score"),
        record.get("financial_score"), record.get("execution_score"),
        record.get("conversion_probability"), record.get("last_interaction_date"),
        red_flags, context_json, record.get("created_at"), record.get("updated_at")
    ))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_prospect(prospect_id: str) -> Optional[dict]:
    """Fetch one prospect by prospect_id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prospects WHERE prospect_id = ?", (prospect_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    if d.get("context_json"):
        try:
            d["context_json"] = json.loads(d["context_json"])
        except (TypeError, json.JSONDecodeError):
            pass
    if d.get("red_flags"):
        try:
            d["red_flags"] = json.loads(d["red_flags"]) if isinstance(d["red_flags"], str) else d["red_flags"]
        except (TypeError, json.JSONDecodeError):
            pass
    return d


def get_all_prospects() -> list:
    """Return all prospects as list of dicts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM prospects ORDER BY prospect_id")
    rows = cur.fetchall()
    conn.close()
    out = []
    for row in rows:
        d = dict(row)
        if d.get("context_json"):
            try:
                d["context_json"] = json.loads(d["context_json"])
            except (TypeError, json.JSONDecodeError):
                pass
        if d.get("red_flags") and isinstance(d["red_flags"], str):
            try:
                d["red_flags"] = json.loads(d["red_flags"])
            except (TypeError, json.JSONDecodeError):
                pass
        out.append(d)
    return out


def update_prospect(prospect_id: str, updates: dict) -> bool:
    """Update prospect by prospect_id. Returns True if row was updated."""
    updates["updated_at"] = datetime.utcnow().isoformat() + "Z"
    if "context_json" in updates and isinstance(updates["context_json"], dict):
        updates["context_json"] = json.dumps(updates["context_json"])
    if "red_flags" in updates and isinstance(updates["red_flags"], list):
        updates["red_flags"] = json.dumps(updates["red_flags"])
    conn = get_connection()
    cur = conn.cursor()
    cols = [k for k in updates if k in (
        "name", "email", "persona", "compartment", "compartment_days",
        "identity_score", "commitment_score", "financial_score", "execution_score",
        "conversion_probability", "last_interaction_date", "red_flags", "context_json", "updated_at"
    )]
    if not cols:
        conn.close()
        return False
    set_clause = ", ".join(f"{c} = ?" for c in cols)
    vals = [updates[c] for c in cols]
    vals.append(prospect_id)
    cur.execute(f"UPDATE prospects SET {set_clause} WHERE prospect_id = ?", vals)
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def delete_prospect(prospect_id: str) -> bool:
    """Delete prospect and related rows. Returns True if deleted."""
    conn = get_connection()
    cur = conn.cursor()
    for t in ("feedback", "chat_history", "interactions", "prospects"):
        cur.execute(f"DELETE FROM {t} WHERE prospect_id = ?", (prospect_id,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


# --- Interactions ---

def insert_interaction(prospect_id: str, interaction_type: str, notes: str = "", outcome: str = "") -> int:
    """Log an interaction. Returns new row id."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat() + "Z"
    cur.execute(
        "INSERT INTO interactions (prospect_id, interaction_type, notes, outcome, created_at) VALUES (?, ?, ?, ?, ?)",
        (prospect_id, interaction_type, notes, outcome, now)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_interactions(prospect_id: str, limit: int = 50) -> list:
    """Get recent interactions for a prospect."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM interactions WHERE prospect_id = ? ORDER BY created_at DESC LIMIT ?",
        (prospect_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Chat history ---

def insert_chat_message(prospect_id: Optional[str], role: str, message: str, context_snapshot: Any = None) -> int:
    """Append a chat message. context_snapshot stored as JSON. Returns new row id."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat() + "Z"
    ctx = json.dumps(context_snapshot) if context_snapshot is not None else None
    cur.execute(
        "INSERT INTO chat_history (prospect_id, role, message, context_snapshot, created_at) VALUES (?, ?, ?, ?, ?)",
        (prospect_id, role, message, ctx, now)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_chat_history(prospect_id: Optional[str], limit: int = 100) -> list:
    """Get recent chat messages, optionally filtered by prospect_id."""
    conn = get_connection()
    cur = conn.cursor()
    if prospect_id:
        cur.execute(
            "SELECT * FROM chat_history WHERE prospect_id = ? ORDER BY created_at ASC LIMIT ?",
            (prospect_id, limit)
        )
    else:
        cur.execute("SELECT * FROM chat_history ORDER BY created_at ASC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Feedback ---

def insert_feedback(prospect_id: Optional[str], recommendation_type: str, user_rating: int, message_id: Optional[int] = None) -> int:
    """Record thumbs up (1) or down (0). Returns new row id."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat() + "Z"
    cur.execute(
        "INSERT INTO feedback (prospect_id, recommendation_type, user_rating, message_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (prospect_id, recommendation_type, user_rating, message_id, now)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_feedback_stats(recommendation_type: Optional[str] = None) -> dict:
    """Aggregate feedback: total, positive count, negative count."""
    conn = get_connection()
    cur = conn.cursor()
    if recommendation_type:
        cur.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN user_rating = 1 THEN 1 ELSE 0 END) as positive FROM feedback WHERE recommendation_type = ?",
            (recommendation_type,)
        )
    else:
        cur.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN user_rating = 1 THEN 1 ELSE 0 END) as positive FROM feedback"
        )
    row = cur.fetchone()
    conn.close()
    total = row["total"] or 0
    positive = row["positive"] or 0
    return {"total": total, "positive": positive, "negative": total - positive}
