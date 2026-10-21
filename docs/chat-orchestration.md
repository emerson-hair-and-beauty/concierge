# Chat orchestration

There are **four** orchestrator-shaped files in this codebase. Only one of
them is wired to a live chat route. This document states what each one does
and whether anything calls it — as a fact, not a recommendation.

## What is actually live

**`app/web_chat_agent/orchestrator.py`** is the orchestrator behind the
real chat endpoints: `POST /api/web/chat` and `POST /api/web/chat/stream`
(`app/web_chat_agent/router.py` imports `orchestrate_web_chat` directly from
this file).

It runs a two-pass flow per message:

1. **`ProfileObserver` (Pass 1)** — a single LLM call extracts hair traits
   (texture, density, moisture behaviour, humidity response, goals) from the
   message and merges them into an in-memory session profile
   (`_session_profile_cache`, keyed by `session_id`). This cache is
   process-local and not persisted — it resets if the process restarts.
2. **Session signals + alerts (Pass 1.5)** — calls
   `process_session_signals` and `process_alerts` (see
   [`signal-detection.md`](signal-detection.md) and `ROADMAP.md`). Failures
   here are caught and swallowed; alerts are best-effort and must not block
   the reply.
3. **Triage (Pass 2)** — a second LLM call splits the message into a list of
   `{"intent": ..., "query": ...}` tasks, where `intent` is `DISCOVERY`,
   `FAQ`, or `ADVISOR`. Each task is dispatched to
   `app/web_chat_agent/discovery_agent.py`, `faq_agent.py`, or
   `hair_advisor_agent.py` respectively, and results are streamed back as
   SSE-style events.

Chat history for this path is held in `_web_chat_history_cache` inside
`router.py` — also in-memory, also process-local.

## What exists but is not wired to any route

**`app/web_chat_agent/orchestrator_v2.py`** — `WebChatOrchestratorV2`. Its
own docstring says it "implements the Decomposer Agent spec in parallel with
the V1 system." Instead of the Triage prompt, it uses `decomposer.py`'s
`Decomposer`, which classifies the message into a journey state
(`DISCOVERING` / `DIAGNOSING` / `EVALUATING` / `CONVERSION_READY`), an
intent, and a problem type, and can short-circuit to a clarifying question
when confidence is low. Nothing in `app/main.py` or any router imports
`orchestrator_v2.py`. The only thing that calls it is
`tests/compare_orchestrators.py`, a manual script that runs three sample
queries through V1 and V2 side by side and prints both outputs for
comparison — it is not a pytest test and asserts nothing.

**`app/agents/web_chat_orchestrator.py`** — a third chat orchestrator,
structurally similar to V1, but importing from a *different* set of agent
files: `app/agents/discovery_agent.py`, `app/agents/faq_agent.py`,
`app/agents/hair_advisor_agent.py` (as opposed to the
`app/web_chat_agent/` versions V1 and V2 both use). Nothing in the codebase
imports this file. It and the three agent files it depends on appear to be
dead code.

## A separate, unrelated feature: the quiz-based routine generator

**`app/agents/orchestrator.py`** is not a chat orchestrator at all, and is
not a duplicate of the above. It is wired to `POST /orchestrator/run-orchestrator`
(`app/api/orchestrator.py`). It takes a one-shot `OrchestratorInput` (a
completed hair-profile questionnaire, not a conversation), and runs a
straight-line pipeline: `collateAdvice` → `generateRoutine` →
`createRecommendations`, saving the result as the user's active routine via
`db.save_routine`. `GET /orchestrator/routine/{user_id}` reads it back. This
is the original quiz → routine → product flow, separate from the
conversational chat system above.

## Open questions

Left unresolved deliberately — see `README.md`'s Open Questions section:

- Is `orchestrator_v2.py` an abandoned experiment, or in-progress work meant
  to replace V1? Nothing in the repo says.
- Is `app/agents/web_chat_orchestrator.py` (and the three agent files it
  depends on) safe to delete, or is it a reference for something in
  progress?
- Two separate session-history caches exist for chat
  (`_session_profile_cache` in `orchestrator.py`, `_web_chat_history_cache`
  in `router.py`), both in-memory and both lost on restart. Whether that is
  intentional for the current stage, or a gap to fix before production load,
  isn't documented anywhere.
