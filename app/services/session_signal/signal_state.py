from datetime import datetime, timezone
from typing import Dict, List

from app.services.supabase_service import get_supabase
from app.services.resilience import safe_call

TABLE = "signal_events"

SIGNAL_NAMES = [
    "absorption_blocked",
    "hold_loss",
    "breakage_active",
    "buildup_present",
    "coated_feel",
    "scalp_sensitivity",
]


def _get_logged_signals(session_id: str) -> List[str]:
    def _fetch() -> List[str]:
        supabase = get_supabase()
        response = (
            supabase.table(TABLE)
            .select("signal_type")
            .eq("session_id", session_id)
            .execute()
        )
        return [row["signal_type"] for row in (response.data or [])]

    return safe_call(
        _fetch,
        fallback=[],
        source="signal_state._get_logged_signals",
        detail=(
            f"Cannot read prior signals for session={session_id!r}. The concierge "
            "will lose memory of anything the user mentioned in earlier turns — e.g. "
            "breakage mentioned once, then forgotten by the next message."
        ),
    )


def log_new_signals(user_id: str, session_id: str, detected: Dict[str, bool]) -> List[str]:
    already_logged = _get_logged_signals(session_id)

    def _write() -> List[str]:
        supabase = get_supabase()
        newly_logged = []
        for signal_type, is_present in detected.items():
            if signal_type not in SIGNAL_NAMES:
                continue
            if is_present and signal_type not in already_logged:
                supabase.table(TABLE).insert({
                    "user_id": user_id,
                    "session_id": session_id,
                    "signal_type": signal_type,
                    "first_detected_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
                newly_logged.append(signal_type)
        return newly_logged

    return safe_call(
        _write,
        fallback=[],
        source="signal_state.log_new_signals",
        detail=(
            f"Could not persist newly detected signals for session={session_id!r}. "
            "They will not be remembered on the next turn."
        ),
    )


def get_session_snapshot(session_id: str) -> Dict[str, bool]:
    active = _get_logged_signals(session_id)
    return {signal: signal in active for signal in SIGNAL_NAMES}
