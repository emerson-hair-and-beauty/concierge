# Concierge — Emerson AI Hair Concierge

This is the backend for Emerson Hair and Beauty's AI concierge. It chats with
curly-hair customers, tracks their hair state across a session, and
recommends routines and products from Emerson's own catalog, in Emerson's
brand voice.

The backend is a FastAPI app (`app/main.py`). It has two live surfaces:

- **The main app** (`app/main.py`) — chat, recommendations, alerts, user
  routes. This is what `render.yaml` deploys as `concierge-api`.
- **Phase 1** (`app/phase1_main.py`) — a separate, feature-flagged
  personalized-plan service, gated by `PHASE1_ENABLED`. `render.phase1.yaml`
  deploys this as `concierge-phase1-api`. See the `PHASE1_*.md` files at the
  repo root for its full spec.

## Architecture at a glance

**There are four ways to have a conversation with this system.** Three are
customer-facing API routes; the fourth is an internal chat surface that
runs the most advanced pipeline of the four, but isn't reachable by a
customer today.

1. `POST /api/chat` — the simplest: one LLM call
   (`app/agents/empath_diagnostic.py`). Internally called "Empath" — see
   `app/api/CHAT_OPTIMIZATION_PROPOSAL.md`.
2. `POST /api/web/chat` / `/chat/stream` — the two-pass Observer + Triage
   system. See [`docs/chat-orchestration.md`](docs/chat-orchestration.md).
3. `POST /orchestrator/run-orchestrator` — not really a chat turn at all; a
   one-shot quiz-answers-to-routine pipeline. Also covered in
   [`docs/chat-orchestration.md`](docs/chat-orchestration.md).
4. **The dashboard chat** (`dashboard.py`, run with `streamlit run
   dashboard.py`) — a genuine `st.chat_input` / `st.chat_message` chat UI,
   with its own message history and its own clarification-question flow,
   that drives the full decision-state → JTE → response-composer pipeline
   end to end (plus a built-in blind A/B mode for comparing tone variants
   on stakeholders). This is internal tooling, not a customer-facing
   surface, but it is the one place this pipeline is actually live and
   conversational today. See
   [`docs/decision-state-and-tone.md`](docs/decision-state-and-tone.md).

Within the path used by (2), two more stages run on every message:

- **Signal detection** — scans the conversation for six hair-health signals
  (breakage, buildup, hold loss, and so on). See
  [`docs/signal-detection.md`](docs/signal-detection.md).
- **Alerts** — turns signals plus weather context into proactive prompts.
  Documented in [`ROADMAP.md`](ROADMAP.md).

**Only reachable through mode 4 above, not through modes 1–3:** the
decision-state engine, JTE delivery plans, and the brand-voice prose
composer (`app/services/decision_state/`), session intent detection
(`app/services/session_intent/`), and the Simasia tone-guard classifier.
These are real, tested subsystems, and partially reused by Phase 1 plan
generation — but no customer-facing route calls them. See
[`docs/decision-state-and-tone.md`](docs/decision-state-and-tone.md),
[`docs/session-intent.md`](docs/session-intent.md), and
[`docs/tone-guard-and-simasia.md`](docs/tone-guard-and-simasia.md).

- **Recommendations** — a Pinecone-backed product search over Emerson's
  catalog. See [`docs/recommendations.md`](docs/recommendations.md).

Supporting subsystems:

- [`docs/clarification.md`](docs/clarification.md) — follow-up questions
  when the system is not confident enough to answer directly.
- [`docs/review-tooling.md`](docs/review-tooling.md) — the human review loop
  the brand expert uses to approve or reject draft replies.
- [`docs/enrichment-klaviyo.md`](docs/enrichment-klaviyo.md) — the pipeline
  that connects Klaviyo customer exports to signal detection.
- [`docs/testing.md`](docs/testing.md) — what is actually tested, and how to
  run it.
- [`ROADMAP.md`](ROADMAP.md) — environmental factors (hard water, sweat) and
  the alerts pipeline.
- [`TONE_HANDOFF.md`](TONE_HANDOFF.md) — the narrative history of the tone
  system: what broke, what was learned, and why.
- [`PUSH_NOTIFICATIONS_SETUP.md`](PUSH_NOTIFICATIONS_SETUP.md) — web push
  setup.

## API surface

| Router | Mounted at | Routes |
|---|---|---|
| `app/api/chat.py` | `/api` | `POST /chat`, `POST /chat/stream`, `POST /chat/warmup`, `POST /event`, `GET /vitals/{user_id}`, `GET /events/{user_id}`, `DELETE /session/{session_id}` |
| `app/api/orchestrator.py` | `/orchestrator` | `POST /run-orchestrator`, `GET /routine/{user_id}` |
| `app/api/recommendations.py` | `/api` | `GET /recommendations/{user_id}`, `POST /push/subscribe`, `DELETE /push/subscribe` |
| `app/api/scenarios.py` | `/api/scenarios` | `POST /run` (the daily cron entry point for alert rules) |
| `app/api/search.py` | `/search` | `POST /products` |
| `app/api/user.py` | `/api/user` | `POST /wash`, `POST /location`, `GET /alerts`, `POST /alerts/{alert_id}/read` |
| `app/web_chat_agent/router.py` | `/api/web` | `POST /chat`, `POST /chat/stream` |
| `app/services/plans/runtime.py` | — (Phase 1, mounted only if `PHASE1_ENABLED=true`) | see `PHASE1_API_CONTRACT.md` |

Two chat paths exist side by side — `app/api/chat.py` and
`app/web_chat_agent/router.py` — backed by two different orchestrators. See
the Open Questions section below.

## Running locally

1. Create and activate a Python virtual environment, then install
   dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt
   ```

2. Create `app/.env` with the keys the code actually reads. As of this
   writing, that is:

   ```
   LLM_PROVIDER=openai        # or "gemini"
   OPENAI_API_KEY=
   GEMINI_API_KEY=
   PINECONE_API_KEY=
   PINECONE_INDEX=
   SUPABASE_URL=
   SUPABASE_KEY=
   WEATHER_API_KEY=
   OPEN_WEATHER_API_KEY=
   VAPID_PRIVATE_KEY=
   KLAVIYO_PRIVATE_API_KEY=
   KLAVIYO_LIST_ID=
   ```

   Never commit this file — `.gitignore` already excludes `.env` and
   `.env.*`, keeping only `.env.example`-style files.

3. Run the main app:

   ```bash
   uvicorn app.main:app --reload
   ```

   Or run Phase 1 on its own:

   ```bash
   python3 -m pip install -r requirements-phase1.txt
   PHASE1_ENABLED=true uvicorn app.phase1_main:app --reload
   ```

4. Run the real test suite — see
   [`docs/testing.md`](docs/testing.md) for which files in `tests/` are
   actual tests versus demo scripts.

`README.dev.md` predates this file and only mentions `GEMINI_API_KEY`. Treat
this file as current and that one as superseded.

## Open questions

These surfaced while writing this documentation and were deliberately left
unresolved rather than guessed at:

- **Two chat orchestrators.** `app/agents/orchestrator.py` and
  `app/web_chat_agent/orchestrator.py` (plus `orchestrator_v2.py`) all exist.
  No document says which is canonical, and `tests/compare_orchestrators.py`
  suggests this was an open, active comparison. See
  [`docs/chat-orchestration.md`](docs/chat-orchestration.md).
- **"Empath" naming — resolved.** This is the internal name for
  `app/agents/empath_diagnostic.py`, the implementation behind
  `POST /api/chat`. Not a mystery, just undocumented until now.
- **The bigger open question:** is the decision-state/tone-composition
  engine and Simasia tone guard meant to graduate from the dashboard (mode
  4) into one of the three customer-facing paths, stay internal-only and
  feed Phase 1 instead, or something else? Nothing in the repo says.
- **Two tables the code expected didn't exist in Supabase — fixed.** Confirmed
  missing by querying the live database directly (2026-10-21):
  `push_subscriptions` (read/written by
  `app/services/recommendations/push_service.py`, for Web Push) and
  `routine_recommendations` (backing `GET
  /api/recommendations/{user_id}`'s adaptive-nudges feature). The fix already
  existed in the repo, unused — `sql/01_recommendations_tables.sql`. Ran it
  against the live database on 2026-10-21; both tables now exist.
