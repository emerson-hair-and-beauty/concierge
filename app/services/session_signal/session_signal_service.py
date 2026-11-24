import asyncio
from typing import Dict, List

from app.services.session_signal.signal_detector import detect_signals, SIGNAL_NAMES
from app.services.session_signal.signal_state import log_new_signals, get_logged_signals


async def process_session_signals(
    user_id: str,
    session_id: str,
    messages: List[Dict[str, str]],
) -> Dict[str, bool]:
    # Always run detection — new signals can surface at any turn
    # log_new_signals is additive: it only persists signals not already on record
    window = messages[-10:]
    # Read the signals of earlier turns while detection runs. The Supabase client
    # blocks, so it runs in a thread and other users are not held up.
    detected, prior = await asyncio.gather(
        detect_signals(window),
        asyncio.to_thread(get_logged_signals, session_id),
    )
    await asyncio.to_thread(log_new_signals, user_id, session_id, detected, prior)

    # Snapshot merges everything logged so far in this session with this turn's
    # detected signals. It is the same as a read after the write above, without the
    # extra read. If Supabase is unreachable, prior is empty (see signal_state.py),
    # so an outage costs only memory of past turns, not the current message too.
    snapshot = {k: k in prior or bool(detected.get(k)) for k in SIGNAL_NAMES}
    snapshot["confidence_score"] = detected.get("confidence_score", 0.0)
    snapshot["evidence_quote"] = detected.get("evidence_quote", "")
    snapshot["fallback_used"] = detected.get("fallback_used", False)
    return snapshot
