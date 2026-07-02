from datetime import datetime, timezone
from typing import List, Set

from app.services.supabase_service import get_supabase
from app.services.resilience import safe_call

TABLE = "decision_state_events"


def _get_logged_states(session_id: str) -> List[str]:
    def _fetch() -> List[str]:
        supabase = get_supabase()
        response = (
            supabase.table(TABLE)
            .select("decision_state")
            .eq("session_id", session_id)
            .execute()
        )
        return [row["decision_state"] for row in (response.data or [])]

    return safe_call(
        _fetch,
        fallback=[],
        source="decision_state_history._get_logged_states",
        detail=(
            f"Cannot read prior decision states for session={session_id!r}. "
            "Repeat-state suppression breaks this turn — e.g. climate_control_first "
            "may be served again instead of progressing to hold_and_definition_first."
        ),
    )


def log_decision_state(user_id: str, session_id: str, decision_state: str | None) -> None:
    if not decision_state:
        return
    if decision_state in _get_logged_states(session_id):
        return

    def _write() -> None:
        supabase = get_supabase()
        supabase.table(TABLE).insert({
            "user_id": user_id,
            "session_id": session_id,
            "decision_state": decision_state,
            "first_seen_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

    safe_call(
        _write,
        fallback=None,
        source="decision_state_history.log_decision_state",
        detail=(
            f"Could not persist decision_state={decision_state!r} for session={session_id!r}. "
            "This turn's diagnosis will not be remembered on the next turn."
        ),
    )


def get_session_decision_states(session_id: str) -> Set[str]:
    return set(_get_logged_states(session_id))
