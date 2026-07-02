from app.services.decision_state.models import (
    ProfileState,
    SessionSignal,
    EnvironmentalContext,
    SessionIntent,
    RoutineConstraints,
    ProductFilters,
    TextureModifiers,
    JTEInput,
    StrategyPayload,
)
from app.services.decision_state.texture_modifiers import resolve_texture_modifiers

# Decision states where a structural/clinical concern already dictates the routine —
# texture-driven styling emphasis (cast, elongation) should not compete with that.
_STRUCTURAL_PRIORITY_STATES = {"repair_first", "reset_first", "scalp_calm_first"}

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

    # Scalp sensitivity is a separate pathway from buildup — soothing, not clarifying
    if signal.scalp_sensitivity:
        return "scalp_calm_first"

    # Reset signals: waxy coat, buildup, blocked absorption, hard water
    # These win even on a low-elasticity profile — you can't repair through a coat
    if (
        signal.buildup_present
        or signal.coated_feel
        or signal.absorption_blocked
        or env.hard_water
    ):
        return "reset_first"

    # Profile baseline: low elasticity nudges toward repair only when no live signal fired.
    # Yield to climate routing when humidity is the dominant stressor — elasticity is structural,
    # but climate-driven frizz is not a structural failure and needs a different pathway.
    high_humidity_context = env.humidity_level == "high" or (
        profile.humidity_response and "high" in profile.humidity_response.lower()
    )
    if profile.elasticity == "low" and not high_humidity_context:
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
    if decision_state == "scalp_calm_first":
        return RoutineConstraints(
            step_count_target=4,
            mandatory_steps=["gentle_cleanse", "scalp_treatment", "light_condition"],
            forbidden_steps=["protein_mask", "heavy_treatment", "heat_style", "manipulation_heavy"],
        )
    if decision_state == "climate_control_first":
        return RoutineConstraints(
            step_count_target=5,
            mandatory_steps=["cleanse", "condition", "anti_humectant_styler", "sealant"],
            forbidden_steps=["humectant_heavy_styler"],
        )
    if decision_state == "hold_and_definition_first":
        return RoutineConstraints(
            step_count_target=5,
            mandatory_steps=["cleanse", "condition", "gel_or_cast", "seal"],
            forbidden_steps=["heavy_butter", "heavy_oil_pre_poo"],
        )
    if decision_state == "reinforce_current_routine":
        return RoutineConstraints(
            step_count_target=4,
            mandatory_steps=["maintain_current_steps"],
            forbidden_steps=[],
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
    if decision_state == "scalp_calm_first":
        return ProductFilters(
            required_flags=["sulfate_free", "silicone_free"],
            forbidden_flags=["protein", "heavy_butter", "heavy_oil"],
            porosity_match=profile.porosity,
            texture_match=profile.texture_type,
        )
    if decision_state == "climate_control_first":
        return ProductFilters(
            required_flags=["anti_humectant", "humidity_shield"],
            forbidden_flags=["humectant_heavy"],
            ideal_hold_level="strong",
            porosity_match=profile.porosity,
            texture_match=profile.texture_type,
        )
    if decision_state == "hold_and_definition_first":
        return ProductFilters(
            required_flags=["anti_humectant"],
            forbidden_flags=["humectant_heavy", "heavy_butter"],
            ideal_hold_level="strong",
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

    # Density check — hold level target. Texture-driven adjustment (definition_difficulty)
    # is applied uniformly across all decision states by _apply_texture_modifiers_to_filters,
    # not just this standard-flow branch.
    if profile.density == "high":
        hold_level = "strong"
    elif profile.density == "low":
        hold_level = "light"

    return ProductFilters(
        required_flags=required,
        forbidden_flags=forbidden,
        ideal_hold_level=hold_level,
        porosity_match=profile.porosity,
        texture_match=profile.texture_type,
    )


# ---------------------------------------------------------------------------
# Step 2b: Texture modifiers — apply parametric traits without a rule per texture
# ---------------------------------------------------------------------------

def _apply_texture_modifiers_to_routine(
    decision_state: str | None,
    constraints: RoutineConstraints,
    mods: TextureModifiers,
) -> RoutineConstraints:
    mandatory = list(constraints.mandatory_steps)
    forbidden = list(constraints.forbidden_steps)

    # Fragile texture: protect against heavy manipulation regardless of decision state.
    if mods.fragility_index == "high" and "manipulation_heavy" not in forbidden:
        forbidden.append("manipulation_heavy")

    # Styling emphasis only when a structural/clinical concern isn't already dictating steps.
    if decision_state not in _STRUCTURAL_PRIORITY_STATES:
        if mods.shrinkage_factor == "high" and "stretch_or_elongate" not in mandatory:
            mandatory.append("stretch_or_elongate")
        if mods.definition_difficulty == "high" and "gel_or_cast" not in mandatory:
            mandatory.append("gel_or_cast")

    return constraints.model_copy(update={"mandatory_steps": mandatory, "forbidden_steps": forbidden})


def _apply_texture_modifiers_to_filters(
    decision_state: str | None,
    filters: ProductFilters,
    mods: TextureModifiers,
) -> ProductFilters:
    required = list(filters.required_flags)
    hold_level = filters.ideal_hold_level

    # Fragile texture: bias toward protein/strengthening products, unless the decision
    # state has explicitly forbidden protein (e.g. scalp_calm_first).
    if (
        mods.fragility_index == "high"
        and "protein" not in filters.forbidden_flags
        and "protein" not in required
    ):
        required.append("protein")

    # Hard-to-define texture: bump hold level, unless a structural concern already owns
    # the hold decision (repair/reset/scalp-calm leave hold unset on purpose).
    if (
        mods.definition_difficulty == "high"
        and decision_state not in _STRUCTURAL_PRIORITY_STATES
        and hold_level != "strong"
    ):
        hold_level = "strong"

    return filters.model_copy(update={
        "required_flags": required,
        "ideal_hold_level": hold_level,
        "texture_modifiers": mods,
    })


# ---------------------------------------------------------------------------
# Step 3: Secondary decision states
# ---------------------------------------------------------------------------

def _resolve_secondary_state(
    intent: SessionIntent,
    signal: SessionSignal,
    env: EnvironmentalContext,
    profile: ProfileState,
    delivered_states: frozenset[str] = frozenset(),
) -> str:
    # Overwhelmed / high-friction users need simplification first
    if intent.friction_score == "high" or intent.confidence_level == "overwhelmed":
        return "simplify_and_reduce_friction"

    # Positive pattern — routine is working, reinforce consistency.
    # User is satisfied, low friction, not actively describing a problem.
    if (
        intent.emotional_state in ("hopeful", "neutral")
        and intent.friction_score == "low"
        and intent.journey_state not in ("diagnosing", "troubleshooting", "post_purchase")
        and not signal.hold_loss
    ):
        return "reinforce_current_routine"

    # Post-purchase: specific product usage questions — not a climate or repair moment
    if intent.journey_state == "post_purchase":
        return "balanced_routine_first"

    # Climate-driven frizz and definition collapse (supersedes hold_loss — humidity is root cause)
    high_humidity_profile = (
        profile.humidity_response and "high" in profile.humidity_response.lower()
    )
    if env.humidity_level == "high" or high_humidity_profile:
        # Climate education only needs to happen once per session — progress the
        # conversation forward instead of repeating the same diagnosis every turn.
        if "climate_control_first" not in delivered_states:
            return "climate_control_first"
        if "hold_and_definition_first" not in delivered_states:
            return "hold_and_definition_first"
        return "balanced_routine_first"

    # Structure and hold loss without climate as primary driver
    if signal.hold_loss:
        return "hold_and_definition_first"

    return "balanced_routine_first"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_strategy_payload(
    profile: ProfileState,
    signal: SessionSignal,
    env: EnvironmentalContext,
    intent: SessionIntent,
    delivered_states: frozenset[str] = frozenset(),
) -> StrategyPayload:
    # Step 1 — hard overrides
    decision_state = _resolve_hard_override(signal, env, profile)

    # Step 3 — secondary states (only if no hard override)
    if decision_state is None:
        decision_state = _resolve_secondary_state(intent, signal, env, profile, delivered_states)

    print(f"[DecisionEngine] decision_state={decision_state}")

    # Step 2 — conflict resolution produces constraints and filters
    routine_constraints = _resolve_routine_constraints(decision_state, profile)
    product_filters = _resolve_product_filters(decision_state, profile, env)

    # Step 2b — texture modifiers tune the result in place, without a rule per texture
    texture_mods = resolve_texture_modifiers(profile.texture_type)
    routine_constraints = _apply_texture_modifiers_to_routine(decision_state, routine_constraints, texture_mods)
    product_filters = _apply_texture_modifiers_to_filters(decision_state, product_filters, texture_mods)

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
