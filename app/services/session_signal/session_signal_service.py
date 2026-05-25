from typing import Dict, List

from app.services.session_signal.signal_detector import detect_signals
from app.services.session_signal.signal_state import log_new_signals, get_session_snapshot


async def process_session_signals(
    user_id: str,
    session_id: str,
    messages: List[Dict[str, str]],
) -> Dict[str, bool]:
    window = messages[-10:]
    detected = await detect_signals(window)
    log_new_signals(user_id, session_id, detected)
    snapshot = get_session_snapshot(session_id)
    snapshot["confidence_score"] = detected.get("confidence_score", 0.0)
    snapshot["evidence_quote"] = detected.get("evidence_quote", "")
    snapshot["fallback_used"] = detected.get("fallback_used", False)
    return snapshot
