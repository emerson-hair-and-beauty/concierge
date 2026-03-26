from .classifier import (
    classify_moisture_behaviour,
    classify_porosity,  # alias kept for backward compat
    classify_scalp,
    classify_damage,
    classify_density,
    classify_texture,
    classify_humidity_response,
)

# Core hair profile classifiers → treated as guardrails/constraints
HAIR_PROFILE_CLASSIFIERS = {
    "texture": classify_texture,
    "density": classify_density,
    "moisture_behaviour": classify_moisture_behaviour,
}

# Optional legacy classifiers (if provided)
LEGACY_CLASSIFIERS = {
    "scalp": classify_scalp,
    "damage": classify_damage,
}


def collateAdvice(answers: dict) -> dict:
    """
    Collates classifier outputs (guardrails) and hair goals (objective)
    into a structured advice object for the RoutineAgent.

    Architecture:
      - hair_goals → primary objective (what the routine optimises for)
      - classifier outputs → guardrails/constraints (how to achieve the goal)
      - humidity_response → climate-specific constraint (GCC context)
    """
    directives = {}
    product_needs = {}
    routine_flags = {}

    # --- Guardrail classifiers (core hair profile) ---
    for key, classifier in HAIR_PROFILE_CLASSIFIERS.items():
        # Support both new field name (moisture_behaviour) and legacy alias (porosity)
        value = answers.get(key) or answers.get("porosity") if key == "moisture_behaviour" else answers.get(key)
        if value:
            info = classifier(value)
            directives[key] = info.get("directive", "")
            product_needs[key] = info.get("product_needs", [])
            routine_flags[key] = info.get("routine_flags", [])

    # --- Legacy classifiers (backward compat, if present) ---
    for key, classifier in LEGACY_CLASSIFIERS.items():
        value = answers.get(key)
        if value:
            info = classifier(value)
            directives[key] = info.get("directive", "")
            product_needs[key] = info.get("product_needs", [])
            routine_flags[key] = info.get("routine_flags", [])

    # --- Climate constraint (humidity response) ---
    humidity_answer = answers.get("humidity_response")
    if humidity_answer:
        humidity_info = classify_humidity_response(humidity_answer)
        directives["humidity_response"] = humidity_info.get("directive", "")
        product_needs["humidity_response"] = humidity_info.get("product_needs", [])
        routine_flags["humidity_response"] = humidity_info.get("routine_flags", [])

    # --- Primary objective (hair goals) ---
    hair_goals = answers.get("hair_goals") or []
    goals_label = ", ".join(hair_goals) if hair_goals else "General curl health"

    return {
        "goals": goals_label,          # Primary objective for the RoutineAgent prompt
        "directives": directives,       # Guardrail directives per classifier
        "product_needs": product_needs, # Product category hints per classifier
        "routine_flags": routine_flags  # Flags that constrain routine structure
    }
