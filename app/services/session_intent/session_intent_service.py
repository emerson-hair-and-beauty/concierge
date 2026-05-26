from typing import Dict, List

from app.services.session_intent.intent_detector import detect_intent
from app.services.decision_state.models import SessionIntent


async def process_session_intent(
    messages: List[Dict[str, str]],
    window_size: int = 10,
) -> SessionIntent:
    window = messages[-window_size:]
    result = await detect_intent(window)
    return SessionIntent(
        journey_state=result["journey_state"],
        intent_clarity=result["intent_clarity"],
        confidence_level=result["confidence_level"],
        friction_score=result["friction_score"],
        emotional_state=result["emotional_state"],
    )
