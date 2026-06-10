from datetime import datetime, timezone
from typing import List, Set

from app.services.supabase_service import get_supabase

TABLE = "decision_state_events"


def _get_logged_states(session_id: str) -> List[str]:
    supabase = get_supabase()
    response = (
        supabase.table(TABLE)
        .select("decision_state")
        .eq("session_id", session_id)
        .execute()
    )
    return [row["decision_state"] for row in (response.data or [])]


def log_decision_state(user_id: str, session_id: str, decision_state: str | None) -> None:
    if not decision_state:
        return
    if decision_state in _get_logged_states(session_id):
        return

    supabase = get_supabase()
    supabase.table(TABLE).insert({
        "user_id": user_id,
        "session_id": session_id,
        "decision_state": decision_state,
        "first_seen_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def get_session_decision_states(session_id: str) -> Set[str]:
    return set(_get_logged_states(session_id))
