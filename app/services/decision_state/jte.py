from app.services.decision_state.models import JTEInput, JTEDeliveryPlan

# Readiness score weights
_POSITIVE = {"intent_clarity": {"high": 2, "medium": 1, "low": 0},
             "confidence_level": {"certain": 2, "unsure": 1, "overwhelmed": 0}}

_NEGATIVE = {"friction_score": {"high": 2, "moderate": 1, "low": 0},
             "emotional_state": {"frustrated": 2, "fatigued": 1, "neutral": 0, "hopeful": -1}}


def _compute_readiness(jte_input: JTEInput) -> tuple[int, str]:
    score = (
        _POSITIVE["intent_clarity"].get(jte_input.intent_clarity, 0)
        + _POSITIVE["confidence_level"].get(jte_input.confidence_level, 0)
        - _NEGATIVE["friction_score"].get(jte_input.friction_score, 0)
        - _NEGATIVE["emotional_state"].get(jte_input.emotional_state, 0)
    )
    if score >= 6:
        band = "high"
    elif score >= 3:
        band = "medium"
    else:
        band = "low"
    return score, band


def resolve_delivery_plan(jte_input: JTEInput, decision_state: str | None) -> JTEDeliveryPlan:
    readiness_score, readiness_band = _compute_readiness(jte_input)
    journey = jte_input.journey_state
    emotion = jte_input.emotional_state
    friction = jte_input.friction_score

    # Defaults
    response_mode = "educate"
    response_depth = "medium"
    cta_pressure = "soft"
    product_exposure = "selective"
    tone_profile = "warm_reassuring"
    ask_strategy = "proceed_with_best_guess"

    # Hard overrides from decision state
    if decision_state in ("repair_first", "reset_first"):
        response_mode = "educate"
        response_depth = "long"
        cta_pressure = "none"
        product_exposure = "selective"
        ask_strategy = "proceed_with_best_guess"
        # Tone adapts to emotional state even inside repair/reset
        if emotion in ("frustrated", "fatigued") or readiness_band == "low":
            tone_profile = "warm_reassuring"
        else:
            tone_profile = "expert_calm"

    elif decision_state == "simplify_friction":
        response_mode = "reassure"
        response_depth = "short"
        cta_pressure = "none"
        product_exposure = "hidden"
        tone_profile = "simplified_supportive"
        ask_strategy = "one_clarifying_question"

    elif journey == "conversion_ready" and readiness_band == "high":
        response_mode = "convert"
        response_depth = "short"
        cta_pressure = "strong"
        product_exposure = "direct"
        tone_profile = "direct_confident"
        ask_strategy = "no_question"

    elif journey in ("diagnosing", "troubleshooting") or friction == "high":
        response_mode = "troubleshoot" if journey == "troubleshooting" else "educate"
        response_depth = "long"
        cta_pressure = "none"
        product_exposure = "hidden" if readiness_band == "low" else "selective"
        tone_profile = "expert_calm"
        ask_strategy = "one_clarifying_question"

    elif journey == "evaluating":
        response_mode = "compare"
        response_depth = "medium"
        cta_pressure = "moderate"
        product_exposure = "selective"
        tone_profile = "direct_confident"
        ask_strategy = "no_question"

    elif emotion in ("frustrated", "fatigued"):
        response_mode = "reassure"
        response_depth = "medium"
        cta_pressure = "soft"
        product_exposure = "selective"
        tone_profile = "warm_reassuring"
        ask_strategy = "proceed_with_best_guess"

    elif readiness_band == "high":
        response_mode = "convert"
        response_depth = "short"
        cta_pressure = "moderate"
        product_exposure = "routine_led"
        tone_profile = "direct_confident"
        ask_strategy = "no_question"

    print(
        f"[JTE] journey={journey} | readiness={readiness_band}({readiness_score}) | "
        f"decision={decision_state} | mode={response_mode} | depth={response_depth} | "
        f"cta={cta_pressure} | exposure={product_exposure}"
    )

    return JTEDeliveryPlan(
        response_mode=response_mode,
        response_depth=response_depth,
        cta_pressure=cta_pressure,
        product_exposure=product_exposure,
        tone_profile=tone_profile,
        ask_strategy=ask_strategy,
        readiness_band=readiness_band,
        readiness_score=readiness_score,
    )
