from typing import Dict, List

from app.services.session_signal.signal_detector import detect_signals, SIGNAL_NAMES
from app.services.session_signal.signal_state import log_new_signals, get_session_snapshot


async def process_session_signals(
    user_id: str,
    session_id: str,
    messages: List[Dict[str, str]],
) -> Dict[str, bool]:
    # Check what we already know for this session
    existing = get_session_snapshot(session_id)
    already_active = any(existing.get(k) for k in SIGNAL_NAMES)

    if already_active:
        # Signals are already established — don't re-run detection, move forward
        print(f"[SessionSignal] Active signals already on record, skipping detection.")
        existing["confidence_score"] = 1.0
        existing["evidence_quote"] = ""
        existing["fallback_used"] = False
        return existing

    window = messages[-10:]
    detected = await detect_signals(window)
    log_new_signals(user_id, session_id, detected)
    snapshot = get_session_snapshot(session_id)
    snapshot["confidence_score"] = detected.get("confidence_score", 0.0)
    snapshot["evidence_quote"] = detected.get("evidence_quote", "")
    snapshot["fallback_used"] = detected.get("fallback_used", False)
    return snapshot
