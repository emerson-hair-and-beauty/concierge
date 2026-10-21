# Decision state and tone composition

Lives in `app/services/decision_state/`. This is the most sophisticated
subsystem in the codebase, and it is the engine behind **mode 4** in
`README.md`'s architecture overview: the interactive chat built into
`dashboard.py` (`streamlit run dashboard.py`), not any of the three
customer-facing routes. It is also exercised by offline evaluation scripts,
and partially reused by Phase 1 plan generation
(`app/services/plans/generator.py`, which uses only
`build_strategy_payload`, not the full chain below).

Concretely: when someone types a message into the dashboard's chat box,
it runs every layer described below — signal detection, session intent,
the decision engine, the JTE, and the response composer — and the Simasia
tone guard scores the result. That is a real, working, conversational
chat experience. It is just one a customer never sees, because nothing in
`app/api/` or `app/web_chat_agent/` calls into this folder.

It is a four-layer pipeline, each layer a plain Python model in `models.py`:

## Layer 1 — Inputs

Four inputs, built elsewhere and assembled here:

- `ProfileState` — biological baseline (texture type, porosity, density,
  elasticity, scalp state, hair goals)
- `SessionSignal` — the six signals from
  [`signal-detection.md`](signal-detection.md)
- `EnvironmentalContext` — humidity, heat, hard water, from `ROADMAP.md`'s
  environmental-factors services
- `SessionIntent` — journey state, friction, emotion, from
  [`session-intent.md`](session-intent.md)

## Layer 2 — The Decision Engine (`decision_engine.py`)

Entirely rules-based, no LLM call. `build_strategy_payload()` runs in three
steps:

1. **Hard overrides**, checked in order: active breakage → `repair_first`;
   scalp sensitivity → `scalp_calm_first`; buildup, coated feel, blocked
   absorption, or hard water → `reset_first`; low elasticity (and not a
   high-humidity context) → `repair_first`.
2. If no hard override fires, **secondary states** are resolved from
   session intent and signals: high friction or an overwhelmed user →
   `simplify_and_reduce_friction`; a satisfied, low-friction user →
   `reinforce_current_routine`; high humidity → `climate_control_first`
   (once per session — it tracks which states were already delivered and
   progresses to `hold_and_definition_first` next rather than repeating
   itself); hold loss → `hold_and_definition_first`; otherwise
   `balanced_routine_first`.
3. Whichever `decision_state` results shapes `RoutineConstraints` (mandatory
   / forbidden routine steps) and `ProductFilters` (required / forbidden
   product flags, hold level), then both are nudged further by
   `texture_modifiers.py` — a lookup table mapping curl pattern (2A–4C) to
   three coarse traits (shrinkage, fragility, definition difficulty), so
   texture-specific behavior doesn't need a hand-written branch per pattern.

Output: a `StrategyPayload`, plus a `JTEInput` summarizing the session
intent fields for the next layer.

## Layer 3 — The JTE (`jte.py`)

"JTE" is used throughout as a proper noun but is never expanded anywhere in
the codebase or docs — what it stands for is unknown to this documentation
pass.

Also rules-based. `resolve_delivery_plan()` first computes a numeric
`readiness_score` (clarity + confidence − friction − emotional resistance,
banded into low/medium/high), then picks six delivery parameters —
`response_mode` (educate/reassure/compare/convert/troubleshoot),
`response_depth` (short/medium/long), `cta_pressure`, `product_exposure`,
`tone_profile` (expert_calm/warm_reassuring/direct_confident/simplified_supportive),
and `ask_strategy` — through a chain of `if/elif` rules: a `decision_state`
hard override from Layer 2 takes priority, then journey state, then
emotional state, then readiness band.

Output: a `JTEDeliveryPlan`.

## Layer 4 — The Response Composer (`response_composer.py`)

One LLM call. Builds a prompt from four independent instruction blocks —
tone (warmth only), depth (length only), CTA pressure, and product
exposure — plus a response-mode structure template (e.g. `educate` →
Observation → Interpretation → Recommendation → Why) and an internal,
never-shown-to-the-user explanation of the decision state.

Two things worth knowing if you touch this file:

- **The internal decision-state notes are written as clipped fragments, not
  full sentences, on purpose.** An earlier version wrote them as polished
  prose, and the model quoted that prose verbatim into customer replies
  (5 of 5 generated replies repeated "buildup or a waxy coating" from the
  `reset_first` note). If you edit `_DECISION_EXPLANATIONS`, don't write a
  sentence you'd be comfortable seeing in a live reply.
- **The structure templates were reverted once already** after a blind
  A/B test (`ed7cedf1db2a` vs `847425ed0fc1` — see `TONE_HANDOFF.md`). A
  version that opened every reply by naming a cause scored 2/8 approved
  against the current version's 5/8. Check `TONE_HANDOFF.md` before
  changing `_RESPONSE_STRUCTURES` or `_SHORT_STRUCTURES` again.

The composer imports `tone_guard` and `tone_rules` — see
[`tone-guard-and-simasia.md`](tone-guard-and-simasia.md).

## A second, simpler, also-dead router

`router.py` and `decision_state_resolver.py` are a separate, much simpler
path through this same folder: `resolve_decision_state()` checks only two
signals (breakage → `repair_first`, buildup/absorption-blocked →
`reset_first`) and dispatches to canned prompts in `response_handlers.py`,
falling back to `app/agents/orchestrator.py` for everything else. **Nothing
in the codebase calls `router.route()`** — not even `dashboard.py` or the
test suite. This appears to be an earlier, abandoned version of the same
idea the four-layer pipeline above now does more completely.

## Persistence

`decision_state_history.py` logs each session's `decision_state` values to
Supabase's `decision_state_events` table, read back via
`get_session_decision_states()` — this is what lets the decision engine
avoid repeating `climate_control_first` twice in one session. Same
degrade-to-empty-on-outage pattern as `signal_state.py`.
