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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS time_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_seconds REAL,
            baseline_seconds REAL,
            time_saved_seconds REAL,
            created_at TEXT,
            FOREIGN KEY (prospect_id) REFERENCES prospects(prospect_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT NOT NULL,
            outcome_type TEXT NOT NULL,
            value REAL,
            notes TEXT,
            created_at TEXT,
            FOREIGN KEY (prospect_id) REFERENCES prospects(prospect_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS weekly_roi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start_date TEXT UNIQUE NOT NULL,
            time_saved_hours REAL DEFAULT 0,
            revenue_projection REAL DEFAULT 0,
            clients_contacted INTEGER DEFAULT 0,
            clients_advanced INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
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


# --- Time tracking ---

def insert_time_tracking(prospect_id: str, activity_type: str, started_at: str, ended_at: Optional[str] = None,
                        duration_seconds: Optional[float] = None, baseline_seconds: Optional[float] = None,
                        time_saved_seconds: Optional[float] = None) -> int:
    now = datetime.utcnow().isoformat() + "Z"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO time_tracking (prospect_id, activity_type, started_at, ended_at, duration_seconds,
           baseline_seconds, time_saved_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (prospect_id, activity_type, started_at, ended_at, duration_seconds, baseline_seconds, time_saved_seconds, now)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_time_saved_total() -> float:
    """Total time_saved_seconds across all records (for display as hours)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(time_saved_seconds), 0) as total FROM time_tracking")
    row = cur.fetchone()
    conn.close()
    return (row["total"] or 0) / 3600.0


def get_time_tracking_by_week(weeks: int = 12) -> list:
    """List of {date, time_saved_hours} by day for recent activity."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT date(started_at) as d, SUM(COALESCE(time_saved_seconds, 0)) / 3600.0 as hours
        FROM time_tracking WHERE ended_at IS NOT NULL
        GROUP BY date(started_at) ORDER BY d DESC LIMIT ?
    """, (weeks * 7,))
    rows = cur.fetchall()
    conn.close()
    return [{"date": row["d"], "time_saved_hours": round(row["hours"] or 0, 2)} for row in rows]


def get_usage_dates() -> list:
    """Distinct dates (YYYY-MM-DD) when any time_tracking activity was recorded (for consecutive-day count)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date(created_at) as d FROM time_tracking ORDER BY d DESC LIMIT 30")
    rows = cur.fetchall()
    conn.close()
    return [row["d"] for row in rows if row["d"]]


# --- Outcomes ---

def insert_outcome(prospect_id: str, outcome_type: str, value: Optional[float] = None, notes: Optional[str] = None) -> int:
    now = datetime.utcnow().isoformat() + "Z"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO outcomes (prospect_id, outcome_type, value, notes, created_at) VALUES (?, ?, ?, ?, ?)",
        (prospect_id, outcome_type, value or 0, notes, now)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_outcomes_count(outcome_type: Optional[str] = None) -> int:
    conn = get_connection()
    cur = conn.cursor()
    if outcome_type:
        cur.execute("SELECT COUNT(*) as c FROM outcomes WHERE outcome_type = ?", (outcome_type,))
    else:
        cur.execute("SELECT COUNT(*) as c FROM outcomes")
    row = cur.fetchone()
    conn.close()
    return row["c"] or 0


def has_any_advancement() -> bool:
    return get_outcomes_count("advancement") > 0


# --- Weekly ROI ---

def upsert_weekly_roi(week_start_date: str, time_saved_hours: float = 0, revenue_projection: float = 0,
                     clients_contacted: int = 0, clients_advanced: int = 0) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO weekly_roi (week_start_date, time_saved_hours, revenue_projection, clients_contacted, clients_advanced, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(week_start_date) DO UPDATE SET
            time_saved_hours = excluded.time_saved_hours,
            revenue_projection = excluded.revenue_projection,
            clients_contacted = excluded.clients_contacted,
            clients_advanced = excluded.clients_advanced,
            updated_at = excluded.updated_at
    """, (week_start_date, time_saved_hours, revenue_projection, clients_contacted, clients_advanced, now, now))
    conn.commit()
    conn.close()


def get_weekly_roi(weeks: int = 12) -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM weekly_roi ORDER BY week_start_date DESC LIMIT ?", (weeks,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
