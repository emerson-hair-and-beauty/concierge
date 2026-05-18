from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.services.supabase_service import get_supabase
from app.services.alerts.alert_types import Alert

TABLE = "alert_log"


def _latest_sent_at_by_type(user_id: str) -> Dict[str, datetime]:
    """Most recent sent_at per alert_type for this user. Used by cooldown checks."""
    supabase = get_supabase()
    response = (
        supabase.table(TABLE)
        .select("alert_type, sent_at")
        .eq("user_id", user_id)
        .order("sent_at", desc=True)
        .execute()
    )
    latest: Dict[str, datetime] = {}
    for row in (response.data or []):
        alert_type = row["alert_type"]
        if alert_type in latest:
            continue
        sent_at_raw = row["sent_at"]
        latest[alert_type] = datetime.fromisoformat(sent_at_raw.replace("Z", "+00:00"))
    return latest


def _is_on_cooldown(last_sent: Optional[datetime], cooldown_days: Optional[int]) -> bool:
    if last_sent is None:
        return False
    if cooldown_days is None:
        return True  # never re-fire
    return datetime.now(timezone.utc) - last_sent < timedelta(days=cooldown_days)


def filter_unsent(user_id: str, alerts: List[Alert]) -> List[Alert]:
    """Drop alerts whose cooldown window hasn't elapsed since the last send."""
    latest = _latest_sent_at_by_type(user_id)
    return [
        a for a in alerts
        if not _is_on_cooldown(latest.get(a.alert_type), a.cooldown_days)
    ]


def log_sent(user_id: str, alert: Alert) -> None:
    supabase = get_supabase()
    supabase.table(TABLE).insert({
        "user_id": user_id,
        "source_type": alert.source_type,
        "source_id": alert.source_id,
        "alert_type": alert.alert_type,
        "scenario": alert.scenario or alert.alert_type,
        "prompt": alert.message,
        "is_read": False,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def get_unread_alerts(user_id: str, limit: int = 3) -> List[Dict]:
    """Banner-inbox query. Returns the same shape the frontend already reads."""
    supabase = get_supabase()
    response = (
        supabase.table(TABLE)
        .select("id, user_id, scenario, prompt, is_read, sent_at")
        .eq("user_id", user_id)
        .eq("is_read", False)
        .order("sent_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = response.data or []
    # Preserve the legacy field name `created_at` so the frontend contract holds.
    for row in rows:
        row["created_at"] = row.pop("sent_at")
    return rows


def mark_read(alert_id: str) -> bool:
    supabase = get_supabase()
    try:
        supabase.table(TABLE).update({"is_read": True}).eq("id", alert_id).execute()
        return True
    except Exception as e:
        print(f"[alert_state] mark_read failed: {e}")
        return False
