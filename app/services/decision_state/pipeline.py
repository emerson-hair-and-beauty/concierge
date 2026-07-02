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
from app.services.decision_state.decision_state_history import (
    get_session_decision_states,
    log_decision_state,
)
from app.services.decision_state.jte import resolve_delivery_plan
from app.services.decision_state.response_composer import compose_response
from app.agents.recommendation.lib.knowledge_base.query_products import query_products
from app.services.clarification.clarification_generator import generate_clarification
from app.services.session_signal.signal_detector import SIGNAL_NAMES


# Layer 1 — Decision state core: what the hair needs right now
_DECISION_STATE_TERMS = {
    "repair_first":                 "protein treatment bond repair breakage prevention elasticity restoration",
    "reset_first":                  "clarifying shampoo chelating buildup removal deep cleanse residue",
    "scalp_calm_first":             "sensitive scalp soothing gentle cleanser anti-inflammatory fragrance free",
    "climate_control_first":        "anti-humectant glycerin free humidity resistant frizz shield strong hold",
    "hold_and_definition_first":    "strong hold curl gel definition frizz control cast method curl keeper",
    "reinforce_current_routine":    "curl care moisture balance maintenance scalp health",
    "simplify_and_reduce_friction": "lightweight leave-in simple routine easy curl care moisture",
    "balanced_routine_first":       "curl care leave-in moisturiser styler hydration definition maintenance",
}

# Layer 2 — Active signal terms: what the user is experiencing
_SIGNAL_TERMS = {
    "absorption_blocked": "moisture penetration absorption barrier low porosity humectant",
    "hold_loss":          "curl definition hold longevity frizz control structure",
    "breakage_active":    "breakage repair strengthening protein fragile weak strands",
    "buildup_present":    "scalp cleanse clarify residue removal buildup sebum",
    "coated_feel":        "silicone free lightweight film remover clarify waxy coating",
    "scalp_sensitivity":  "sensitive scalp gentle soothing mild fragrance free",
}

# Layer 3 — Profile modifiers: who the hair belongs to
_POROSITY_TERMS = {
    "low":    "low porosity lightweight formula humectant",
    "medium": "medium porosity balanced moisture protein",
    "high":   "high porosity occlusive sealant protein rich",
}

# Layer 3b — Texture modifier terms: only added when a trait is "high" (low/medium
# textures don't need extra emphasis in an already-crowded query)
_MODIFIER_QUERY_TERMS = {
    "shrinkage_factor":      "shrinkage elongation stretching length retention",
    "fragility_index":       "gentle low manipulation strengthening fragile hair protection",
    "definition_difficulty": "strong definition curl clumping structure hold cast",
}

_TEXTURE_TERMS = {
    "4C": "4C tight coils shrinkage moisture retention",
    "4B": "4B dense coils definition moisture",
    "4A": "4A defined coils spiral moisture",
    "3C": "3C tight curls frizz definition",
    "3B": "3B defined curls medium hold",
    "3A": "3A loose curls lightweight bounce",
    "2C": "2C wavy frizz control light hold",
    "2B": "2B wavy lightweight",
    "2A": "2A soft waves mousse gel",
}


def _build_product_query(decision_state: str, active_signals: list, filters) -> str:
    parts = []

    layer1 = _DECISION_STATE_TERMS.get(decision_state, "curl care moisturiser")
    parts.append(layer1)

    for signal in active_signals:
        term = _SIGNAL_TERMS.get(signal)
        if term:
            parts.append(term)

    porosity_term = _POROSITY_TERMS.get(filters.porosity_match or "")
    if porosity_term:
        parts.append(porosity_term)

    texture_term = _TEXTURE_TERMS.get(filters.texture_match or "")
    if texture_term:
        parts.append(texture_term)

    if filters.texture_modifiers:
        for field, term in _MODIFIER_QUERY_TERMS.items():
            if getattr(filters.texture_modifiers, field) == "high":
                parts.append(term)

    return " ".join(parts)


# Keep for dashboard backwards compatibility
_PRODUCT_QUERY_TEMPLATES = _DECISION_STATE_TERMS
_POROSITY_CONTEXT = _POROSITY_TERMS
_TEXTURE_CONTEXT = _TEXTURE_TERMS

# Maps decision_engine.py's ProductFilters flag vocabulary onto the flags
# actually present in Pinecone metadata (see index_product_matrix.py _build_flags).
# Flags with no indexed equivalent (e.g. anti_humectant, bond_builder, chelating)
# are intentionally omitted — they have no effect until the catalogue is enriched.
_FORBIDDEN_FLAG_ALIASES = {
    "humectant_heavy": "humectant_heavy",
    "heavy_butter":    "butter_oil_heavy",
    "heavy_oil":       "butter_oil_heavy",
    "protein":         "protein",
}

_REQUIRED_FLAG_ALIASES = {
    "sulfate_free":       "sulfate_free",
    "silicone_free":      "silicone_free",
    "low_buildup_risk":   "low_buildup_risk",
    "lightweight_formula": "lightweight",
    "protein":            "protein",
}

# Acceptable indexed `hold` values for each ideal_hold_level.
_HOLD_MATCH = {
    "light":    {"none", "soft"},
    "moderate": {"soft", "medium"},
    "strong":   {"medium", "strong"},
}


def _score_product(product: dict, filters) -> int:
    metadata = product.get("metadata") or {}
    flags = set(metadata.get("flags", []))
    score = 0

    for flag in filters.forbidden_flags:
        indexed = _FORBIDDEN_FLAG_ALIASES.get(flag)
        if indexed and indexed in flags:
            score -= 2

    for flag in filters.required_flags:
        indexed = _REQUIRED_FLAG_ALIASES.get(flag)
        if indexed and indexed in flags:
            score += 1

    if filters.ideal_hold_level:
        acceptable = _HOLD_MATCH.get(filters.ideal_hold_level, set())
        if metadata.get("hold") in acceptable:
            score += 1

    return score


def _rerank_products(products: list, filters, top_n: int) -> list:
    """Re-orders semantically-retrieved products so ones that violate the
    decision state's known required/forbidden flags and hold level sink to
    the bottom, without dropping below top_n results."""
    ranked = sorted(
        enumerate(products),
        key=lambda pair: (-_score_product(pair[1], filters), pair[0]),
    )
    return [product for _, product in ranked[:top_n]]


async def _fetch_candidate_products(payload, session_signal=None, shown_product_ids: set = None) -> list:
    filters = payload.product_filters
    decision_state = payload.decision_state or "balanced_routine_first"
    active_signals = [k for k in SIGNAL_NAMES if getattr(session_signal, k, False)] if session_signal else []

    query = _build_product_query(decision_state, active_signals, filters)
    result = await query_products(query, top_k=15)
    ranked = _rerank_products(result.get("products", []), filters, top_n=15)

    if shown_product_ids:
        fresh = [p for p in ranked if p.get("id") not in shown_product_ids]
        return fresh[:5] if len(fresh) >= 3 else ranked[:5]

    return ranked[:5]


async def run_concierge_pipeline(
    user_id: str,
    session_id: str,
    messages: List[Dict[str, str]],
    profile: ProfileState,
    env: EnvironmentalContext,
    conversation_summary: str | None = None,
    shown_product_ids: set = None,
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

    delivered_states = get_session_decision_states(session_id)
    strategy_payload = build_strategy_payload(profile, session_signal, env, session_intent, frozenset(delivered_states))
    log_decision_state(user_id, session_id, strategy_payload.decision_state)
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
        candidate_products = await _fetch_candidate_products(strategy_payload, session_signal=session_signal, shown_product_ids=shown_product_ids or set())

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
