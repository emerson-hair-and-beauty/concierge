# Session intent

Lives in `app/services/session_intent/`. One LLM call
(`intent_detector.py`) classifies the last 10 messages of a conversation
across five dimensions:

- `journey_state` — discovering / diagnosing / evaluating / conversion_ready
  / reassurance / post_purchase / troubleshooting
- `intent_clarity` — low / medium / high
- `confidence_level` — certain / unsure / overwhelmed
- `friction_score` — low / moderate / high
- `emotional_state` — frustrated / hopeful / neutral / fatigued

`session_intent_service.py`'s `process_session_intent()` wraps this into a
`SessionIntent` object (defined in
`app/services/decision_state/models.py` — this module's output type is
owned by decision_state, not by session_intent itself).

On any detector exception, it returns a fixed neutral default
(`discovering` / `low` / `unsure` / `low` / `neutral`) rather than raising.

**Important:** this is not called from either customer-facing web-chat
orchestrator. Its only caller is `app/services/decision_state/pipeline.py`.
See [`decision-state-and-tone.md`](decision-state-and-tone.md) — that
pipeline is the engine behind the dashboard's chat (mode 4 in `README.md`),
so session intent detection does run live, just not during a real customer
chat. It also runs in several offline scripts
(`scripts/replay_whatsapp.py`, `tests/chat_demo.py`,
`tests/demo_pipeline.py`, `tests/qa_scenarios.py`).
