# Testing

There is no `pytest.ini` or `conftest.py` anywhere in this repo. Nothing in
`tests/` is pytest-style in practice, even where the filename suggests it.
Here is what's actually there, grouped by what it really is.

## The 14 `test_*.py` files — read-the-console-output scripts

`test_alerts_e2e.py`, `test_alerts_pipeline.py`, `test_classifiers_new.py`,
`test_decision_routing.py`, `test_decomposer.py`, `test_enrichment.py`,
`test_full_weather.py`, `test_hard_water.py`, `test_phase1.py`,
`test_session_signals.py`, `test_signal_scenarios.py`, `test_simasia.py`,
`test_sweat_logic.py`, `test_tone_guard.py`.

Checked directly: **zero of these contain a single `assert` statement.**
Three define a function named `test_...()` (`test_decomposer.py`,
`test_hard_water.py`, `test_sweat_logic.py`); the rest run top-level code
under `if __name__ == "__main__":`. Every one follows the same hand-rolled
pattern (confirmed in `test_hard_water.py` and `test_sweat_logic.py`, and
consistent with the no-assert finding in all 14): loop over cases, compare
actual vs. expected, print `PASS` or `FAIL` per case, print a final
"All tests passed" / "Some tests FAILED" line.

**This means two things in practice:**

- **Run them with `python tests/test_whatever.py`, not `pytest`.** None
  declare a dependency on the pytest runner, and most aren't importable as
  a plain test module anyway (several, like `test_session_signals.py`,
  make live calls to Gemini using a real API key rather than mocking).
- **A failure does not fail loud.** No file calls `sys.exit` on a failed
  case (confirmed — no file in `tests/` calls `sys.exit` at all) and
  there's no `assert` to raise `AssertionError`. Even if these were run
  under `pytest`, they would be reported as passed regardless of how many
  `FAIL` lines they printed, because nothing in them signals failure to a
  test runner. Reading the printed `PASS`/`FAIL` lines is currently the
  only way to know whether a run succeeded.

## Demo and comparison scripts — not tests at all, despite living here

- **`chat_demo.py`**, **`demo_pipeline.py`** — print what the pipeline
  decided at each stage, for a human to read. `demo_pipeline.py`'s own
  header calls itself a demo.
- **`compare_orchestrators.py`** — runs the same queries through the live
  web-chat orchestrator (V1) and the unwired `orchestrator_v2.py` side by
  side and prints both. See
  [`chat-orchestration.md`](chat-orchestration.md).
- **`qa_scenarios.py`** — runs 30 feedback scenarios through the
  decision-state pipeline (not live — see
  [`decision-state-and-tone.md`](decision-state-and-tone.md)) and prints
  the routing decisions.
- **`routing_cases.py`** — not runnable itself; shared fixture data (data
  only, no network calls) for the routing scripts above. Its own docstring
  carries an important caveat worth repeating here: the expected signals
  and intent in each fixture are **beliefs about what the detectors would
  say, not measured output** — nothing in these fixtures actually runs
  `detect_signals` or `process_session_intent`. A clean run of anything
  built on `routing_cases.py` shows the decision engine routes correctly
  *given* an assumed detector reading. It says nothing about whether the
  detectors actually produce that reading on real input.

## Generated output, not code

`phase1_demo_plans.json`, `phase1_generation_results.json`,
`phase1_https_responses.txt`, `phase1_legacy_qa_results.json`,
`phase1_live_diagnostics_responses.txt`, `phase1_load_results.json`,
`phase1_openapi.json` — recorded output from running the `scripts/phase1_*`
checks, committed into `tests/` alongside the actual test code. They are
artifacts, not tests, and reading them tells you what a past run produced,
not whether the current code still produces it.

## If you want this to fail loud

None of the above currently can, on its own, break a CI run or exit
non-zero. That's a real gap if automated testing matters going forward —
noted here as a fact about the current state, not a task taken on by this
documentation pass.
