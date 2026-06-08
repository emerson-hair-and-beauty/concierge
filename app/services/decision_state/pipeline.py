import asyncio
import json
from typing import AsyncGenerator, Dict, List

from app.services.decision_state.models import (
    ProfileState,
    EnvironmentalContext,
    ResponseComposerInput,
)
from app.services.session_signal.session_signal_service import process_session_signals
from app.services.session_intent.session_intent_service import process_session_intent
from app.services.decision_state.decision_engine import build_strategy_payload
from app.services.decision_state.jte import resolve_delivery_plan
from app.services.decision_state.response_composer import compose_response
from app.agents.recommendation.lib.knowledge_base.query_products import query_products
from app.services.clarification.clarification_generator import generate_clarification
from app.services.session_signal.signal_detector import SIGNAL_NAMES


_PRODUCT_QUERY_TEMPLATES = {
    "repair_first": (
        "hydrolyzed protein treatment bond builder amino acid keratin repair "
        "elasticity restoration breakage prevention strengthening fragile hair"
    ),
    "reset_first": (
        "clarifying shampoo chelating treatment scalp buildup removal "
        "deep cleanse product residue hard water mineral deposit"
    ),
    "hold_first": (
        "strong hold curl gel anti humectant humidity resistant definition "
        "frizz control sealant high humidity curl keeper"
    ),
    "simplify_friction": (
        "simple easy curl routine leave-in conditioner lightweight moisture"
    ),
}

_POROSITY_CONTEXT = {
    "low":    "lightweight formula low porosity hair humectant avoid heavy oils",
    "medium": "balanced moisture protein medium porosity curl care",
    "high":   "high porosity porous hair occlusive sealant protein rich moisturiser",
}

_TEXTURE_CONTEXT = {
    "4C": "tight coils 4C shrinkage prone fragile moisture retention",
    "4B": "dense coils 4B definition moisture rich curl care",
    "4A": "loose coils 4A defined spiral moisture",
    "3C": "tight curls 3C frizz prone humidity definition",
    "3B": "defined curls 3B curl cream medium hold",
    "3A": "loose curls 3A lightweight moisture bounce",
    "2C": "wavy 2C frizz control light hold",
    "2B": "wavy 2B lightweight enhancing",
    "2A": "soft waves 2A mousse light gel",
}


async def _fetch_candidate_products(payload) -> list:
    filters = payload.product_filters
    decision_state = payload.decision_state or "balanced_routine_first"

    base = _PRODUCT_QUERY_TEMPLATES.get(decision_state, "curl care moisturiser styler")
    porosity_ctx = _POROSITY_CONTEXT.get(filters.porosity_match or "", "")
    texture_ctx = _TEXTURE_CONTEXT.get(filters.texture_match or "", "")

    query = f"{base} {porosity_ctx} {texture_ctx}".strip()
    result = await query_products(query, top_k=5)
    return result.get("products", [])


async def run_concierge_pipeline(
    user_id: str,
    session_id: str,
    messages: List[Dict[str, str]],
    profile: ProfileState,
    env: EnvironmentalContext,
    conversation_summary: str | None = None,
) -> AsyncGenerator:
    # --- Phase 1: Run all input services in parallel ---
    yield json.dumps({"type": "status", "content": "Analysing your situation..."}) + "\n"

    signal_task = process_session_signals(user_id, session_id, messages)
    intent_task = process_session_intent(messages)

    signal_snapshot, session_intent = await asyncio.gather(signal_task, intent_task)

    print(f"[Pipeline] signal={signal_snapshot} | intent={session_intent}")

    # --- Clarification gate: ask if we genuinely can't read the signal ---
    no_active_signals = not any(signal_snapshot.get(k) for k in SIGNAL_NAMES)
    low_confidence = signal_snapshot.get("confidence_score", 0) < 0.5
    if no_active_signals and low_confidence:
        print("[Pipeline] Inconclusive signals — generating clarification request")
        clarification = await generate_clarification(messages)
        yield json.dumps({
            "type": "clarification",
            "content": clarification.model_dump(),
        }) + "\n"
        return

    # --- Phase 2: Decision Engine (pure rules, instant) ---
    from app.services.decision_state.models import SessionSignal
    session_signal = SessionSignal(**{
        k: signal_snapshot[k]
        for k in SessionSignal.model_fields
        if k in signal_snapshot
    })

    strategy_payload = build_strategy_payload(profile, session_signal, env, session_intent)
    yield json.dumps({
        "type": "strategy",
        "content": strategy_payload.model_dump(),
    }) + "\n"

    # --- Phase 3: JTE (pure rules, instant) ---
    delivery_plan = resolve_delivery_plan(strategy_payload.jte_input, strategy_payload.decision_state)
    yield json.dumps({
        "type": "delivery_plan",
        "content": delivery_plan.model_dump(),
    }) + "\n"

    # --- Phase 4: Fetch products (skip if hidden) ---
    candidate_products = []
    if delivery_plan.product_exposure != "hidden":
        yield json.dumps({"type": "status", "content": "Finding relevant products..."}) + "\n"
        candidate_products = await _fetch_candidate_products(strategy_payload)

    # --- Phase 5: Response Composer (LLM call, streamed) ---
    yield json.dumps({"type": "status", "content": "Composing response..."}) + "\n"

    composer_input = ResponseComposerInput(
        strategy_payload=strategy_payload,
        jte_delivery_plan=delivery_plan,
        profile_state=profile,
        env=env,
        candidate_products=candidate_products,
        recent_messages=messages[-6:],
        conversation_summary=conversation_summary,
    )

    async for chunk in compose_response(composer_input):
        yield json.dumps(chunk) + "\n"
