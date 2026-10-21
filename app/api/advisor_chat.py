"""
Advisor Chat — HTTP surface for the decision-state pipeline.

`app/services/decision_state/pipeline.py`'s `run_concierge_pipeline` already
implements the full signal-detection -> intent -> decision-engine -> JTE ->
product-search -> response-composer chain as a ready-to-stream async
generator (the same one `dashboard.py` exercises by hand for internal
testing). This module is the thin HTTP wrapper that was missing: it builds
`ProfileState` / `EnvironmentalContext` from a user's stored profile and
hands everything else straight to that generator, unchanged.

Streaming follows the same newline-delimited-JSON convention
`run_concierge_pipeline` already yields (one `json.dumps(...) + "\\n"` line
per event), matching `/orchestrator/run-orchestrator`'s existing streaming
style rather than introducing a second framing convention.
"""

import json
import traceback
from collections import defaultdict
from typing import Dict, List, Set

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.decision_state.models import ProfileState, EnvironmentalContext
from app.services.decision_state.pipeline import run_concierge_pipeline
from app.services.environmental_factors.hard_water_service import get_water_hardness

router = APIRouter(tags=["advisor_chat"])

# In-memory chat history for this surface, same pattern as
# app/web_chat_agent/router.py's _web_chat_history_cache — process-local,
# lost on restart, consistent with the other live chat paths' current state.
_advisor_history_cache: Dict[str, List[Dict[str, str]]] = defaultdict(list)

# Product ids already shown per session, so later turns surface fresh products
# (same freshness rule dashboard.py applies via shown_product_ids).
_advisor_shown_products: Dict[str, Set[str]] = defaultdict(set)


class AdvisorChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


def _get_history(session_id: str, limit: int = 10) -> List[Dict[str, str]]:
    history = _advisor_history_cache.get(session_id, [])
    return history[-limit:] if limit else history


def _append_history(session_id: str, role: str, content: str) -> None:
    _advisor_history_cache[session_id].append({"role": role, "content": content})


def _build_profile(metadata: Dict) -> ProfileState:
    """Best-effort ProfileState from user_metadata. Falls back to medium/
    unspecified values when onboarding data is missing, rather than failing
    the request — a chat reply with generic assumptions is better than no
    reply. `texture_modifiers.resolve_texture_modifiers` expects bare codes
    ("3C"), but onboarding stores "Type 3C" (see useOnboardingStore.js) —
    strip the prefix so the lookup actually matches.
    """
    raw_texture = (metadata.get("texture") or "").strip()
    texture_type = raw_texture.replace("Type ", "").strip() or "3B"

    porosity_raw = (metadata.get("moisture_behaviour") or "medium porosity").lower()
    porosity = "low" if "low" in porosity_raw else "high" if "high" in porosity_raw else "medium"

    density_raw = (metadata.get("density") or "medium").lower()
    density = "low" if "low" in density_raw else "high" if "high" in density_raw else "medium"

    return ProfileState(
        texture_type=texture_type,
        texture_label=raw_texture or "Unspecified",
        porosity=porosity,
        density=density,
        humidity_response=metadata.get("humidity_response"),
        hair_goals=metadata.get("hair_goals") or [],
    )


def _build_environmental_context(metadata: Dict) -> EnvironmentalContext:
    """Hard water only, for v1 — classifying live weather into the
    low/medium/high bands EnvironmentalContext expects needs a mapping this
    pass doesn't build (see the plan's note on this). humidity_level /
    heat_stress stay None, which the decision engine already treats as
    "not a high-humidity context" rather than erroring.
    """
    location = metadata.get("location")
    if not location:
        return EnvironmentalContext()
    return EnvironmentalContext(hard_water=get_water_hardness(location) == "hard")


@router.post("/chat/stream")
async def advisor_chat_stream(request: AdvisorChatRequest):
    history = _get_history(request.session_id)
    _append_history(request.session_id, "user", request.message)
    messages = history + [{"role": "user", "content": request.message}]

    async def event_generator():
        from app.services.db_service import get_db

        db = get_db()
        metadata = db.get_user_metadata(request.user_id) or {}
        profile = _build_profile(metadata)
        env = _build_environmental_context(metadata)

        full_reply = ""
        shown = _advisor_shown_products[request.session_id]
        try:
            async for line in run_concierge_pipeline(
                request.user_id, request.session_id, messages, profile, env,
                shown_product_ids=shown,
            ):
                event = json.loads(line)
                if event.get("type") == "content":
                    full_reply += event.get("content", "")
                elif event.get("type") == "products":
                    shown.update(p["id"] for p in event.get("content", []) if p.get("id"))
                yield line
        except Exception:
            # The HTTP status is already 200 by the time any line has been
            # yielded (streaming has started), so a mid-stream failure here
            # cannot surface as a 5xx — it would otherwise just kill the
            # connection silently. Log the real cause server-side and send
            # the client one clean, parseable event instead.
            print(f"[AdvisorChat] Pipeline failed for session {request.session_id}:")
            print(traceback.format_exc())
            yield json.dumps({
                "type": "error",
                "content": "Something went wrong generating a response. Please try again.",
            }) + "\n"
            return

        if full_reply:
            _append_history(request.session_id, "assistant", full_reply)

    return StreamingResponse(event_generator(), media_type="text/plain")
