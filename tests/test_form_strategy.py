"""Offline tests: do the routine form answers reach the decision engine?

The routine form (`/orchestrator/run-orchestrator`) now runs the same decision
engine as the advisor chat before it writes the routine. These tests check
that the form answers pick the correct main need. If they fail, a form user
gets a routine that ignores what they ticked.

No network, no LLM.

Run:
    python -m unittest tests.test_form_strategy -v
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agents.orchestrator import build_form_strategy  # noqa: E402
from app.agents.routine.lib.routine_prompt import routine_prompt  # noqa: E402

# No location: get_water_hardness returns "hard" for every country today, so
# any location forces reset_first. Without a location, the tests reach the
# other rules.
BASE = {
    "texture": "Type 3B",
    "density": "Medium",
    "moisture_behaviour": "Medium porosity",
}


def _state(**extra) -> str:
    with redirect_stdout(io.StringIO()):
        return build_form_strategy({**BASE, **extra}).decision_state


class FormStrategyTests(unittest.TestCase):
    def test_breakage_tick_gives_repair(self):
        # Breakage is damage to the strand. It must come before all other needs.
        self.assertEqual(_state(concerns=["breakage_active", "buildup_present"]), "repair_first")

    def test_buildup_tick_gives_reset(self):
        # Products cannot get through a coat, so the routine must clear it first.
        self.assertEqual(_state(concerns=["buildup_present"]), "reset_first")

    def test_scalp_tick_gives_scalp_calm(self):
        self.assertEqual(_state(concerns=["scalp_sensitivity"]), "scalp_calm_first")

    def test_hold_loss_tick_gives_hold(self):
        self.assertEqual(_state(concerns=["hold_loss"]), "hold_and_definition_first")

    def test_no_ticks_never_gives_reinforce(self):
        # A form user asks for a new routine. "Keep your current routine" is a wrong answer.
        self.assertEqual(_state(), "balanced_routine_first")
        self.assertEqual(_state(concerns=[]), "balanced_routine_first")

    def test_unknown_tick_is_ignored(self):
        # A label the engine does not know must not crash the request.
        self.assertEqual(_state(concerns=["shiny_hair"]), "balanced_routine_first")

    def test_high_humidity_answer_gives_climate(self):
        self.assertEqual(_state(humidity_response="High frizz in humidity"), "climate_control_first")

    def test_gcc_location_gives_reset(self):
        # The engine treats GCC water as hard. This is the same rule as the advisor chat.
        self.assertEqual(_state(location="UAE"), "reset_first")

    def test_prompt_carries_the_plan(self):
        # The routine LLM must see the step count and the steps from the engine.
        with redirect_stdout(io.StringIO()):
            strategy = build_form_strategy({**BASE, "concerns": ["breakage_active"]})
            prompt = routine_prompt({"goals": "Strength", "directives": {}, "routine_flags": {}, "strategy": strategy})
        self.assertIn("repair_first", prompt)
        self.assertIn("4-step", prompt)
        self.assertIn("protein_treatment", prompt)
        self.assertIn("heat_style", prompt)

    def test_prompt_without_plan_is_unchanged(self):
        # Callers that send no strategy keep the old 5-step prompt.
        with redirect_stdout(io.StringIO()):
            prompt = routine_prompt({"goals": "Strength", "directives": {}, "routine_flags": {}})
        self.assertIn("5-step", prompt)
        self.assertNotIn("DECISION ENGINE PLAN", prompt)


if __name__ == "__main__":
    unittest.main()
