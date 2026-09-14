"""Offline routing tests: does a message land in the pipeline it should?

No network, no LLM. Signals and intent are supplied by hand from
`tests/routing_cases.py` — read that module's docstring before reading a green
run as "routing works". These tests check the decision engine, not the detectors
that feed it.

Run:
    python -m unittest tests.test_decision_routing -v
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.decision_state.decision_engine import build_strategy_payload  # noqa: E402
from tests.routing_cases import (  # noqa: E402
    CASES,
    ENV_GCC,
    ENV_HW,
    ENV_LOW,
    ENV_MED,
    P3C,
    P4A,
    P4B,
    P4C_LOW_ELAST,
    intent,
    signal,
)


def state_for(profile, sig, env, sess_intent, delivered=frozenset()) -> str:
    """The decision state, with the engine's debug printing swallowed."""
    with redirect_stdout(io.StringIO()):
        return build_strategy_payload(profile, sig, env, sess_intent, delivered).decision_state


class HardOverrideTests(unittest.TestCase):
    """The first ladder, and the order within it.

    Order is a property of the set, not of any single pipeline, so it is tested
    here once rather than repeated in each pipeline's own class. Each test stacks
    the loser's trigger on top of the winner's and asserts the winner still wins.
    """

    def test_breakage_beats_scalp(self):
        self.assertEqual(
            state_for(P3C, signal(breakage_active=True, scalp_sensitivity=True), ENV_MED, intent()),
            "repair_first",
        )

    def test_scalp_beats_buildup(self):
        self.assertEqual(
            state_for(P3C, signal(scalp_sensitivity=True, buildup_present=True), ENV_MED, intent()),
            "scalp_calm_first",
        )

    def test_buildup_beats_low_elasticity(self):
        # The comment at decision_engine.py:50-51 is the claim under test: you
        # cannot repair through a coat, so reset wins even on a repair profile.
        self.assertEqual(
            state_for(P4C_LOW_ELAST, signal(buildup_present=True), ENV_MED, intent()),
            "reset_first",
        )

    def test_low_elasticity_is_the_floor_of_the_ladder(self):
        self.assertEqual(
            state_for(P4C_LOW_ELAST, signal(), ENV_MED, intent()),
            "repair_first",
        )

    def test_each_reset_trigger_fires_on_its_own(self):
        for name in ("buildup_present", "coated_feel", "absorption_blocked"):
            with self.subTest(trigger=name):
                self.assertEqual(
                    state_for(P3C, signal(**{name: True}), ENV_MED, intent()),
                    "reset_first",
                )

    def test_hard_water_alone_forces_reset(self):
        # Environmental, not a session signal, and easy to miss when picking an
        # env for an unrelated test: ENV_HW routes everything to reset_first.
        self.assertEqual(state_for(P3C, signal(), ENV_HW, intent()), "reset_first")

    def test_low_elasticity_yields_to_high_humidity(self):
        # Elasticity is structural; climate-driven frizz is not. The branch is
        # cancelled by high humidity from *either* source.
        self.assertEqual(
            state_for(P4C_LOW_ELAST, signal(), ENV_GCC, intent()),
            "climate_control_first",
        )
        self.assertEqual(
            state_for(P4B, signal(), ENV_LOW, intent()),
            "climate_control_first",
        )

    def test_no_trigger_falls_through_to_the_secondary_ladder(self):
        self.assertIsNotNone(state_for(P3C, signal(), ENV_MED, intent()))
        self.assertEqual(state_for(P3C, signal(), ENV_MED, intent()), "balanced_routine_first")


class SecondaryStateTests(unittest.TestCase):
    """The second ladder, including the two orderings that surprise people."""

    def test_high_friction_simplifies(self):
        self.assertEqual(
            state_for(P3C, signal(), ENV_MED, intent(friction_score="high")),
            "simplify_and_reduce_friction",
        )

    def test_overwhelmed_simplifies(self):
        self.assertEqual(
            state_for(P3C, signal(), ENV_MED, intent(confidence_level="overwhelmed")),
            "simplify_and_reduce_friction",
        )

    def test_simplify_beats_climate(self):
        self.assertEqual(
            state_for(P4B, signal(), ENV_GCC, intent(friction_score="high")),
            "simplify_and_reduce_friction",
        )

    def test_reinforce_outranks_humidity(self):
        # TRAP 1. A happy customer in Dubai is not a climate problem. Reinforce is
        # checked before the humidity branch, so a settled routine is left alone
        # even in the env that otherwise routes everything to climate.
        self.assertEqual(
            state_for(
                P4B, signal(), ENV_GCC,
                intent(emotional_state="hopeful", friction_score="low", journey_state="reassurance"),
            ),
            "reinforce_current_routine",
        )

    def test_reinforce_needs_all_four_conditions(self):
        base = dict(emotional_state="hopeful", friction_score="low", journey_state="reassurance")
        for override in (
            {"emotional_state": "frustrated"},
            {"friction_score": "moderate"},
            {"journey_state": "troubleshooting"},
        ):
            with self.subTest(override=override):
                self.assertNotEqual(
                    state_for(P3C, signal(), ENV_MED, intent(**{**base, **override})),
                    "reinforce_current_routine",
                )
        # hold_loss is the fourth: a dropping curl is a live problem, whatever the
        # customer's mood says.
        self.assertNotEqual(
            state_for(P3C, signal(hold_loss=True), ENV_MED, intent(**base)),
            "reinforce_current_routine",
        )

    def test_hold_loss_loses_to_humidity(self):
        # TRAP 2. Humidity is the root cause, so it is treated before the symptom.
        self.assertEqual(
            state_for(P3C, signal(hold_loss=True), ENV_GCC, intent()),
            "climate_control_first",
        )

    def test_hold_loss_routes_home_without_humidity(self):
        self.assertEqual(
            state_for(P3C, signal(hold_loss=True), ENV_LOW, intent()),
            "hold_and_definition_first",
        )

    def test_post_purchase_is_not_a_climate_moment(self):
        self.assertEqual(
            state_for(P4B, signal(), ENV_GCC, intent(journey_state="post_purchase")),
            "balanced_routine_first",
        )

    def test_climate_is_taught_once_then_moves_on(self):
        # Repeating the same diagnosis every turn is the failure this guards.
        self.assertEqual(
            state_for(P3C, signal(), ENV_GCC, intent(), frozenset({"climate_control_first"})),
            "hold_and_definition_first",
        )
        self.assertEqual(
            state_for(
                P3C, signal(), ENV_GCC, intent(),
                frozenset({"climate_control_first", "hold_and_definition_first"}),
            ),
            "balanced_routine_first",
        )

    def test_default_is_balanced(self):
        self.assertEqual(state_for(P3C, signal(), ENV_LOW, intent()), "balanced_routine_first")


# ---------------------------------------------------------------------------
# Per-pipeline classes. One per pipeline, added as each is built.
# ---------------------------------------------------------------------------


def case(name: str) -> dict:
    for entry in CASES:
        if entry["name"] == name:
            return entry
    raise KeyError(f"no routing case named {name!r}")


class RepairFirstTests(unittest.TestCase):
    """Pipeline 1. Two ways in: the `breakage_active` signal, or the profile baseline."""

    def test_both_cases_land_in_repair_first(self):
        for name in ("repair_breakage", "repair_low_elasticity"):
            with self.subTest(case=name):
                c = case(name)
                self.assertEqual(
                    state_for(c["profile"], c["expect_signals"], c["env"], c["intent"]),
                    c["expect_state"],
                )

    def test_the_two_triggers_are_genuinely_different_routes(self):
        # If the low-elasticity case also carried a breakage signal, it would be
        # the same test twice and the profile baseline would go unproven.
        self.assertFalse(case("repair_low_elasticity")["expect_signals"].breakage_active)
        self.assertEqual(case("repair_low_elasticity")["profile"].elasticity, "low")
        self.assertEqual(case("repair_breakage")["profile"].elasticity, "normal")

    def test_low_elasticity_route_needs_the_env_to_stay_calm(self):
        # The other half of that trigger. Same customer, humid climate, different
        # pipeline — which is why the env is part of the case, not a detail.
        c = case("repair_low_elasticity")
        self.assertEqual(
            state_for(c["profile"], c["expect_signals"], ENV_GCC, c["intent"]),
            "climate_control_first",
        )

    def test_breakage_alone_is_enough(self):
        # No supporting profile, no supporting env, no supporting intent. The
        # signal carries it by itself.
        self.assertEqual(
            state_for(P4A, signal(breakage_active=True), ENV_LOW, intent()),
            "repair_first",
        )

    def test_breakage_survives_the_climate_that_swallows_everything_else(self):
        # ENV_GCC redirects low-elasticity repair routing to climate. It must not
        # do the same to an active breakage signal — that yield is written for the
        # profile baseline only.
        self.assertEqual(
            state_for(P4B, signal(breakage_active=True), ENV_GCC, intent()),
            "repair_first",
        )

    def test_breakage_survives_overwhelm(self):
        # simplify_and_reduce_friction sits on the secondary ladder, which is only
        # consulted when no hard override fired.
        self.assertEqual(
            state_for(P3C, signal(breakage_active=True), ENV_MED, intent(friction_score="high")),
            "repair_first",
        )

    def test_repair_mandates_protein_and_forbids_heat(self):
        c = case("repair_breakage")
        with redirect_stdout(io.StringIO()):
            payload = build_strategy_payload(c["profile"], c["expect_signals"], c["env"], c["intent"])
        self.assertIn("protein_treatment", payload.routine_constraints.mandatory_steps)
        self.assertIn("heat_style", payload.routine_constraints.forbidden_steps)
        self.assertIn("bond_builder", payload.product_filters.required_flags)
        for flag in ("heavy_butter", "silicone", "mineral_oil"):
            self.assertIn(flag, payload.product_filters.forbidden_flags)

    def test_repair_leaves_styling_emphasis_alone(self):
        # repair_first is a structural-priority state: a hard-to-define texture
        # must not add a cast step on top of a damage routine.
        with redirect_stdout(io.StringIO()):
            payload = build_strategy_payload(P4B, signal(breakage_active=True), ENV_MED, intent())
        self.assertNotIn("gel_or_cast", payload.routine_constraints.mandatory_steps)
        self.assertNotIn("stretch_or_elongate", payload.routine_constraints.mandatory_steps)
        self.assertIsNone(payload.product_filters.ideal_hold_level)


if __name__ == "__main__":
    unittest.main(verbosity=2)
