"""
Sandi Bot - ROI and time-saved calculations.
Baseline times (manual process estimates), weekly aggregation, revenue projection.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Baseline times in seconds (manual process estimates without the app)
BASELINE_SECONDS = {
    "monday_review": 45 * 60,       # 45 min Monday morning review
    "pre_call_prep": 15 * 60,      # 15 min per call prep
    "per_client_session": 12 * 60, # 12 min average per client (prep + decide action)
    "plan_call": 10 * 60,           # 10 min to plan one call manually
    "mark_contacted": 5 * 60,       # 5 min to log and move on
}

# Revenue assumptions for projection (configurable)
AVG_DEAL_VALUE = 5000.0
CONVERSION_LIFT_FROM_APP = 0.05  # e.g. 5% more conversions from better targeting


def time_saved_for_session(baseline_key: str, actual_seconds: float) -> float:
    """Return time_saved_seconds = max(0, baseline - actual)."""
    baseline = BASELINE_SECONDS.get(baseline_key, BASELINE_SECONDS["per_client_session"])
    return max(0.0, baseline - actual_seconds)


def get_week_start(dt: datetime) -> str:
    """Monday-based week start as YYYY-MM-DD."""
    d = dt.date()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def aggregate_week_time_saved(records: List[Dict]) -> float:
    """Sum time_saved_seconds from records and return hours."""
    total = sum(r.get("time_saved_seconds") or 0 for r in records)
    return round(total / 3600.0, 2)


def revenue_projection(time_saved_hours: float, clients_contacted: int, clients_advanced: int) -> float:
    """
    Simple revenue projection: value from extra focus (time saved) and advancement.
    More time saved + more contact/advancement -> higher projected revenue.
    """
    # Time saved can be "reinvested" in more clients; assume $ value per hour saved
    value_per_hour_saved = 150.0  # placeholder $/hr
    from_time = time_saved_hours * value_per_hour_saved
    from_advanced = clients_advanced * AVG_DEAL_VALUE * CONVERSION_LIFT_FROM_APP
    from_contacted = clients_contacted * (AVG_DEAL_VALUE * 0.01)  # small lift per contact
    return round(from_time + from_advanced + from_contacted, 2)


def get_consecutive_usage_days(session_dates: List[str]) -> int:
    """Count consecutive days (including today) from session_dates (YYYY-MM-DD)."""
    if not session_dates:
        return 0
    today = datetime.utcnow().date().isoformat()
    unique = sorted(set(session_dates), reverse=True)
    if unique[0] != today and today not in unique:
        return 0
    count = 0
    d = datetime.utcnow().date()
    for _ in range(30):
        if d.isoformat() in unique:
            count += 1
            d -= timedelta(days=1)
        else:
            break
    return count
