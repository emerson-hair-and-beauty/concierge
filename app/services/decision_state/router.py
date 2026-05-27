import json
from typing import AsyncGenerator, Dict

from app.services.decision_state.decision_state_resolver import resolve_decision_state
from app.services.decision_state.response_handlers import repair_first_handler, reset_first_handler


async def route(
    session_snapshot: Dict,
    environmental_intent: str | None = None,
    user_context: Dict | None = None,
) -> AsyncGenerator:
    user_context = user_context or {}

    # Resolve decision state — session signals take priority, environmental is a fallback
    session_state = resolve_decision_state(session_snapshot)
    decision_state = session_state or environmental_intent

    print(f"[Router] session_state={session_state} | environmental_intent={environmental_intent} | resolved={decision_state}")

    yield json.dumps({"type": "decision_state", "content": decision_state}) + "\n"

    if decision_state == "repair_first":
        async for chunk in repair_first_handler(user_context):
            yield json.dumps(chunk) + "\n"

    elif decision_state == "reset_first":
        async for chunk in reset_first_handler(user_context):
            yield json.dumps(chunk) + "\n"

    else:
        # Standard advisory flow — no critical signals detected
        # Delegates to the existing orchestrator pipeline
        from app.agents.orchestrator import orchestrator
        from app.api.models import OrchestratorInput
        try:
            input_model = OrchestratorInput(**user_context)
            async for chunk in orchestrator(input_model):
                yield chunk
        except Exception as e:
            yield json.dumps({"type": "error", "content": f"Standard advisory flow failed: {str(e)}"}) + "\n"
