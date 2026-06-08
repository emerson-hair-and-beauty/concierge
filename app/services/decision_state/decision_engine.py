from app.services.decision_state.models import (
    ProfileState,
    SessionSignal,
    EnvironmentalContext,
    SessionIntent,
    RoutineConstraints,
    ProductFilters,
    JTEInput,
    StrategyPayload,
)

# ---------------------------------------------------------------------------
# Step 1: Hard overrides — highest priority, checked first
# ---------------------------------------------------------------------------

_REPAIR_REQUIRED_FLAGS = ["bond_builder", "protein_treatment", "strengthening"]
_REPAIR_FORBIDDEN_FLAGS = ["heavy_butter", "silicone", "mineral_oil"]

_RESET_REQUIRED_FLAGS = ["chelating", "clarifying", "low_buildup_risk"]
_RESET_FORBIDDEN_FLAGS = ["silicone", "heavy_butter", "wax"]

_REPAIR_MANDATORY_STEPS = ["gentle_cleanse", "protein_treatment", "moisture_seal"]
_REPAIR_FORBIDDEN_STEPS = ["heavy_styling", "heat_style", "manipulation_heavy"]

_RESET_MANDATORY_STEPS = ["clarify", "condition", "light_styler"]
_RESET_FORBIDDEN_STEPS = ["heavy_treatment", "oil_pre_poo"]


def _resolve_hard_override(
    signal: SessionSignal,
    env: EnvironmentalContext,
    profile: ProfileState,
) -> str | None:
    # Active breakage always takes top priority — structural damage first
    if signal.breakage_active:
        return "repair_first"

    # Reset signals: waxy coat, buildup, blocked absorption, hard water
    # These win even on a low-elasticity profile — you can't repair through a coat
    if (
        signal.buildup_present
        or signal.coated_feel
        or signal.absorption_blocked
        or env.hard_water
    ):
        return "reset_first"

    # Profile baseline: low elasticity nudges toward repair only when no live signal fired
    if profile.elasticity == "low":
        return "repair_first"

    return None


# ---------------------------------------------------------------------------
# Step 2: Conflict resolution — porosity → texture/density → climate
# ---------------------------------------------------------------------------

def _resolve_routine_constraints(
    decision_state: str | None,
    profile: ProfileState,
) -> RoutineConstraints:
    if decision_state == "repair_first":
        return RoutineConstraints(
            step_count_target=4,
            mandatory_steps=_REPAIR_MANDATORY_STEPS,
            forbidden_steps=_REPAIR_FORBIDDEN_STEPS,
        )
    if decision_state == "reset_first":
        return RoutineConstraints(
            step_count_target=4,
            mandatory_steps=_RESET_MANDATORY_STEPS,
            forbidden_steps=_RESET_FORBIDDEN_STEPS,
        )

    # Standard flow — constraints shaped by profile
    mandatory = ["cleanse", "condition", "moisturise", "style"]
    forbidden = []

    if profile.porosity == "low":
        mandatory.append("steam_or_heat_treatment")
        forbidden.append("heavy_oil_pre_poo")
    if profile.porosity == "high":
        mandatory.append("protein_treatment")

    step_count = 5
    if profile.density == "low":
        step_count = 4
        forbidden.append("heavy_treatment")

    return RoutineConstraints(
        step_count_target=step_count,
        mandatory_steps=mandatory,
        forbidden_steps=forbidden,
    )


def _resolve_product_filters(
    decision_state: str | None,
    profile: ProfileState,
    env: EnvironmentalContext,
) -> ProductFilters:
    if decision_state == "repair_first":
        return ProductFilters(
            required_flags=_REPAIR_REQUIRED_FLAGS,
            forbidden_flags=_REPAIR_FORBIDDEN_FLAGS,
            porosity_match=profile.porosity,
            texture_match=profile.texture_type,
        )
    if decision_state == "reset_first":
        return ProductFilters(
            required_flags=_RESET_REQUIRED_FLAGS,
            forbidden_flags=_RESET_FORBIDDEN_FLAGS,
            porosity_match=profile.porosity,
            texture_match=profile.texture_type,
        )

    # Standard flow — filters built from profile, then climate, then texture/density
    required: list[str] = list(profile.routine_flags)
    forbidden: list[str] = []
    hold_level = "moderate"

    # Porosity check — sets product weight caps
    if profile.porosity == "low":
        forbidden += ["heavy_butter", "heavy_oil", "silicone"]
        required.append("lightweight_formula")
    elif profile.porosity == "high":
        required += ["occlusive", "protein"]

    # Climate check — humectant limits
    if env.humidity_level == "high" or (
        profile.humidity_response and "high" in profile.humidity_response.lower()
    ):
        forbidden.append("humectant_heavy")
        required += ["anti_humectant", "humidity_shield"]

    # Texture / density check — hold level targets
    if profile.density == "high" or profile.texture_type in ("4B", "4C", "3C"):
        hold_level = "strong"
    elif profile.density == "low" or profile.texture_type in ("2A", "2B"):
        hold_level = "light"

    return ProductFilters(
        required_flags=required,
        forbidden_flags=forbidden,
        ideal_hold_level=hold_level,
        porosity_match=profile.porosity,
        texture_match=profile.texture_type,
    )


# ---------------------------------------------------------------------------
# Step 3: Secondary decision states
# ---------------------------------------------------------------------------

def _resolve_secondary_state(
    intent: SessionIntent,
    signal: SessionSignal,
    env: EnvironmentalContext,
) -> str | None:
    if intent.friction_score == "high" or intent.confidence_level == "overwhelmed":
        return "simplify_friction"
    if signal.hold_loss:
        return "hold_first"
    return "balanced_routine_first"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_strategy_payload(
    profile: ProfileState,
    signal: SessionSignal,
    env: EnvironmentalContext,
    intent: SessionIntent,
) -> StrategyPayload:
    # Step 1 — hard overrides
    decision_state = _resolve_hard_override(signal, env, profile)

    # Step 3 — secondary states (only if no hard override)
    if decision_state is None:
        decision_state = _resolve_secondary_state(intent, signal, env)

    print(f"[DecisionEngine] decision_state={decision_state}")

    # Step 2 — conflict resolution produces constraints and filters
    routine_constraints = _resolve_routine_constraints(decision_state, profile)
    product_filters = _resolve_product_filters(decision_state, profile, env)

    jte_input = JTEInput(
        journey_state=intent.journey_state,
        intent_clarity=intent.intent_clarity,
        confidence_level=intent.confidence_level,
        friction_score=intent.friction_score,
        emotional_state=intent.emotional_state,
    )

    return StrategyPayload(
        decision_state=decision_state,
        routine_constraints=routine_constraints,
        product_filters=product_filters,
        jte_input=jte_input,
    )
