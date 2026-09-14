"""Shared fixtures for the routing suite: profiles, environments, and one case per pipeline.

Data only. No LLM imports, nothing that touches the network, so anything importing
this stays offline and fast.

READ THIS BEFORE TRUSTING A GREEN RUN
-------------------------------------
Every case carries `expect_signals` and an `intent`. **Those are beliefs about the
detectors, not measurements.** Nothing here runs `detect_signals` or
`process_session_intent` — the routing tests feed the expected signals and intent
straight into `build_strategy_payload` and check where the message lands *given
that reading*.

So a green suite means "the decision engine routes correctly when the detectors
report what we think they will". It does not mean the detectors report that. The
LLM half is checked by `tests/qa_scenarios.py`, which costs real calls and is not
deterministic. Keep the two apart, and never read this suite as "routing works".

Every customer sentence here was invented by an assistant. That is the honest
limit on all of it until there are real chat logs.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.decision_state.models import (  # noqa: E402
    EnvironmentalContext,
    ProfileState,
    SessionIntent,
    SessionSignal,
)

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

P4B = ProfileState(
    texture_type="4B", texture_label="Dense Coils",
    porosity="high", density="high", elasticity="low",
    humidity_response="high sensitivity",
    routine_flags=["seal_moisture", "frizz_control"],
)
P3C = ProfileState(
    texture_type="3C", texture_label="Tight Curls",
    porosity="low", density="medium", elasticity="normal",
    humidity_response="moderate sensitivity",
    routine_flags=["frizz_control"],
)
P4A = ProfileState(
    texture_type="4A", texture_label="Loose Coils",
    porosity="medium", density="high", elasticity="normal",
    humidity_response="low sensitivity",
    routine_flags=["seal_moisture"],
)

# The only profile that reaches the low-elasticity branch. P4B is also low
# elasticity, but its "high sensitivity" satisfies `high_humidity_context` at
# decision_engine.py:61-64, which cancels the branch before it can fire. Without
# this profile that rule is untestable.
P4C_LOW_ELAST = ProfileState(
    texture_type="4C", texture_label="Tight Coils",
    porosity="high", density="medium", elasticity="low",
    humidity_response="low sensitivity",
    routine_flags=["seal_moisture"],
)

# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

ENV_GCC = EnvironmentalContext(humidity_level="high", heat_stress="high", hard_water=False, ac_exposure="high")
ENV_HW = EnvironmentalContext(humidity_level="medium", heat_stress="low", hard_water=True)
ENV_LOW = EnvironmentalContext(humidity_level="low", heat_stress="low", hard_water=False)

# Neutral middle. ENV_HW cannot be used as a plain "medium humidity" env because
# `hard_water=True` is itself a hard override straight to reset_first.
ENV_MED = EnvironmentalContext(humidity_level="medium", heat_stress="low", hard_water=False)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def signal(**kw) -> SessionSignal:
    """A SessionSignal with everything off except what you name."""
    return SessionSignal(**kw)


def intent(**kw) -> SessionIntent:
    """A SessionIntent that fires no secondary rule unless you change something.

    The defaults are picked so `_resolve_secondary_state` falls all the way
    through to `balanced_routine_first`: friction is `moderate` (not high),
    confidence is `unsure` (not overwhelmed), and journey is `discovering` (not
    post_purchase). `neutral` would qualify for `reinforce_current_routine` on
    emotion alone, but `moderate` friction blocks it. So any state a test gets
    back is caused by what that test set, not by a default leaking in.
    """
    return SessionIntent(**{
        "journey_state": "discovering",
        "intent_clarity": "medium",
        "confidence_level": "unsure",
        "friction_score": "moderate",
        "emotional_state": "neutral",
        **kw,
    })


# ---------------------------------------------------------------------------
# The eight pipelines
# ---------------------------------------------------------------------------

ALL_STATES = frozenset({
    "repair_first",
    "reset_first",
    "scalp_calm_first",
    "climate_control_first",
    "hold_and_definition_first",
    "reinforce_current_routine",
    "simplify_and_reduce_friction",
    "balanced_routine_first",
})

# One case per trigger, appended as each pipeline is built. A pipeline with two
# ways in gets two cases — repair_first is reached by a live signal *or* by the
# profile baseline, and those produce different prompts, so both need reviewing.
#
# Fields:
#   name           short key, used by scripts/pipeline_replies.py and the review page
#   title          what the expert sees above the customer quote
#   trigger        one line naming what actually routes it, for the saved record
#   message        what the customer says
#   profile / env  the context it arrives in
#   expect_signals what we believe detect_signals returns — a belief, see module docstring
#   intent         what we believe process_session_intent returns — likewise
#   expect_state   the pipeline it must land in
CASES: list[dict] = []

CASES.append({
    "name": "repair_breakage",
    "title": "Hair snapping when detangling",
    "trigger": "signal breakage_active",
    "message": (
        "my hair keeps snapping when i detangle and theres little broken pieces "
        "all over my shoulders"
    ),
    # P3C, not P4B: P4B's low elasticity would route to repair_first on its own,
    # so a pass would not prove the breakage signal did anything. P3C has normal
    # elasticity, which leaves `breakage_active` as the only thing that can send
    # this message to repair_first.
    "profile": P3C,
    # ENV_MED, not ENV_HW: hard water is a hard override to reset_first and would
    # outrank breakage before it was ever read.
    "env": ENV_MED,
    "expect_signals": signal(breakage_active=True),
    "intent": intent(journey_state="diagnosing"),
    "expect_state": "repair_first",
})

CASES.append({
    "name": "repair_low_elasticity",
    "title": "Hair stretches and stays stretched",
    "trigger": "profile elasticity=low, and humidity is not high",
    # Elasticity language with no snapping in it. Breakage would route here too,
    # and then the profile baseline would prove nothing.
    "message": (
        "when my hair is wet it stretches out really far and just stays there "
        "instead of springing back up"
    ),
    "profile": P4C_LOW_ELAST,
    # The "not humid" half of the trigger, and the reason it is a separate case:
    # in ENV_GCC this exact customer routes to climate_control_first instead.
    "env": ENV_MED,
    "expect_signals": signal(),
    "intent": intent(journey_state="diagnosing"),
    "expect_state": "repair_first",
})
