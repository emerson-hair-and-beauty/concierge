# Phase 1 API contract: quiz to plan

Implementation update, 2026-09-14: [the implementation and supplier handoff](PHASE1_IMPLEMENTATION.md)
and the service's `/openapi.json` define the current contract. They supersede conflicting details below.
`submission_id` is required. The supplier owns catalog sync and calls `POST /api/catalog`.
The frontend sends click events; redirects do not duplicate them. The optional resend endpoint is deferred.
Fixed titles accompany schema-validated personalized explanations. The backend enforces a 30-second total deadline.
The API hostname is configurable; neither a specific URL nor a Shopify proxy is required.

Status: agreed 2026-09-03. Supersedes the 2026-09-02 version, which described a blocking
request and an optional email. Pairs with `PHASE1_FRONTEND_BRIEF.md`, which is the walkthrough.

## Context

The Curl Concierge roadmap puts the quiz on the Shopify site. The quiz posts its answers to this
API. The customer gets a personalised routine by email, and can also read it on a plan page.

Today there is no such endpoint. `POST /orchestrator/run-orchestrator` accepts the right
*input* — `OrchestratorInput` in `app/api/models.py` already carries texture, density,
`moisture_behaviour`, `humidity_response`, `hair_goals`, name, email, location, hair_length —
but it returns a `StreamingResponse` of `text/plain`. A page that renders a summary, a routine
sequence, product cards, and a reason per step cannot parse prose back into sections.

## Decisions taken

- **Quiz lives on Shopify.** The API receives answers as a payload, not as a conversation.
- **One free-text box**, describing the customer's issue. It feeds the concern detector. Optional.
- **Email is required.** It is how the plan is delivered.
- **No auth.** `plan_id` is the identity.
- **Submit and poll.** `POST /api/plan` returns `202` at once and the work continues in the
  background. The customer can close the tab and still get their email.
- **Quiz to plan only.** The conversational chat agent is out of Phase 1 scope.

## Identity

| Id | Minted | Purpose |
|---|---|---|
| `quiz_id` | Client, when question one renders | Joins the journey events to the plan. Client-supplied, so safe to write against and unsafe to read against |
| `submission_id` | Client, when submit is pressed | Idempotency. A retry returns the existing plan rather than making a second |
| `plan_id` | Server, at plan creation | The public reference. Unguessable UUID, never sequential — it is the only thing protecting the plan behind a public link |
| `anonymous_user_id` | Server, per submission | Written to the existing `user_id TEXT` columns so detection telemetry keeps working. Not a front-end concern |

## Endpoints

All under the existing `/api` prefix in `app/main.py`. New router at `app/api/plan.py`.

### `POST /api/plan`

```json
{
  "quiz_id": "b120...",
  "submission_id": "3e77...",
  "texture": "4B",
  "density": "high",
  "moisture_behaviour": "takes ages to get wet",
  "porosity": "low",
  "strand_thickness": "fine",
  "elasticity": "low",
  "scalp_state": "dry",
  "humidity_response": "high",
  "hair_length": "shoulder",
  "hair_goals": ["definition", "growth"],
  "concern_text": "my curls drop by noon and nothing I put on absorbs",
  "location": "Dubai",
  "first_name": "Amara",
  "email": "amara@example.com",
  "marketing_consent": false,
  "source": "shopify_quiz"
}
```

`texture`, `density` and `email` are required. `concern_text` is optional and may be empty.
`quiz_id` is optional, so direct API calls still work. `source` records where the submission came
from, for the roadmap's traffic-source measure.

Returns `202` immediately:

```json
{ "plan_id": "b6f1...", "status": "pending" }
```

A repeated `submission_id` returns the same `plan_id` and does not start a second run.

### `GET /api/plan/{plan_id}`

The status poll and the plan itself, from one endpoint.

While the pipeline runs:

```json
{ "plan_id": "b6f1...", "status": "pending" }
```

When it finishes:

```json
{
  "plan_id": "b6f1...",
  "status": "ready",
  "created_at": "2026-09-03T10:14:22Z",
  "you_told_us": "my curls drop by noon and nothing I put on absorbs",
  "summary": "Your hair is repelling moisture rather than lacking it...",
  "concerns": [
    {"code": "absorption_blocked", "label": "Blocked absorption"},
    {"code": "hold_loss", "label": "Loss of hold"}
  ],
  "climate_note": "Dubai humidity works against a soft cast...",
  "steps": [
    {
      "order": 1,
      "step": "clarify",
      "title": "Clarify",
      "why": "Nothing will absorb until the coating comes off.",
      "products": [
        {
          "sku": "EM-CL-200",
          "shopify_id": "7412...",
          "variant_id": "41988...",
          "handle": "hydrating-cleanser",
          "name": "Hydrating Cleanser",
          "price": "89.00",
          "currency": "AED",
          "why": "Chelating, no silicone."
        }
      ]
    }
  ]
}
```

`status` is `pending`, `ready`, or `failed`.

`you_told_us` is the detector's `evidence_quote`, or null when the box was empty.

`concerns` may be empty. That is a valid plan, driven by profile and climate alone.

This is also the revisit link, reached from the email days later. The body never changes once
`status` is `ready` — the plan is a frozen snapshot, so what the customer opens on Friday matches
what they were told on Tuesday.

Unknown `plan_id` returns `404`. Errors use the existing shape in `app/api/errors.py`.

### `POST /api/plan/{plan_id}/feedback`

```json
{
  "rating": "very_closely | somewhat | not_quite | not_sure",
  "rejected_shopify_ids": ["7412..."],
  "unclear_step": "clarify",
  "note": "free text, optional"
}
```

Returns `202`. Accepts repeat submissions; the latest wins.

### `POST /api/plan/{plan_id}/resend`

```json
{ "email": "amara@example.com" }
```

Sends the plan again, optionally to a corrected address. The first send happens automatically
when the plan is ready — this is a resend, not the delivery mechanism.

### `POST /api/events`

The journey event stream. The envelope, the vocabulary and the client rules are in the Tracking
section of `PHASE1_FRONTEND_BRIEF.md`; the server side is in `PHASE1_FRONTEND_TRACKING.md`.
Returns `202`.

Must accept `text/plain` as well as `application/json`, because `navigator.sendBeacon` cannot set
a JSON content type without triggering a preflight the browser will not run.

### `GET /apps/concierge/go`

```
/apps/concierge/go?plan_id=<id>&shopify_id=<id>
  → write journey_events → 302 /products/<handle>?plan_id=<id>
```

Logs the click, then redirects. Log before redirecting; a click that leaves the page cannot
report afterwards.

## The plan page

```
/apps/concierge/plan/{plan_id}
```

Served through the Shopify App Proxy so it runs on the store domain. It must render from
`plan_id` alone, because the common path into it is an email opened days later in a different
browser.

## How the response gets built

**Code assembles the envelope. The model fills named prose fields.** This is the rule in
`CLAUDE.md` — the model is for judgment calls, not for transforms code can do.

Structured, no LLM needed:

- `steps[].step` — from `RoutineConstraints.mandatory_steps`, built by
  `app/services/decision_state/decision_engine.py`
- `steps[].products` — Pinecone results filtered by `ProductFilters`, joined to the Shopify
  catalog on `sku`
- `concerns` — from the detector
- `decision_state`, and everything derived from it

LLM-filled, from `app/services/decision_state/response_composer.py`:

- `summary`
- `steps[].why`
- `steps[].products[].why`
- `climate_note`

Do not ask the 928-line composer prompt to emit the whole JSON document. Call it for the prose
fields and let code place them. That is where reliability holds.

## Server-side work

1. **`app/api/plan.py`** — the plan endpoints. Register in `app/main.py`.
2. **`sql/create_plans.sql`** —
   `plans(plan_id UUID PK, submission_id TEXT UNIQUE, quiz_id TEXT NULL, anonymous_user_id,
   email, marketing_consent, status, created_at, source, plan_json JSONB, prompt_version,
   ruleset_version)`. The plan body is a write-once JSONB snapshot. This is the one place derived
   output is stored, because the customer must see the same thing on revisit.
3. **`sql/create_plan_feedback.sql`** — one row per feedback submission, keyed on `plan_id`.
4. **The Shopify catalog table** — `sku → shopify_id, variant_id, handle, title, price,
   available`, kept current by our own pipeline against the Shopify Admin API. Without it the plan can name a product but not link
   to it, and `ProductFilters` cannot honour the promise that we never recommend something
   unavailable.
5. **Wire `concern_text` into the detector.** `app/services/session_signal/signal_detector.py`
   reads conversation text. A single free-text answer is the conversation. Empty text must reach
   `_all_clear` and produce a plan, not an error.
6. **Send the email** when the plan reaches `ready`.
7. **CORS.** `app/main.py` currently sets `allow_origins=["*"]` with `allow_credentials=True`.
   Browsers reject that pair. Replace with the Emerson Shopify origin.
8. **Delete `app/api/web_chat.py`.** It is dead — nothing imports it, and it would raise
   `ImportError` because it imports `WebChatRequest` from `app.api.models`, where that class does
   not exist. The live router is `app/web_chat_agent/router.py`.

## Data model prerequisites

From the separate migration plan, Phase 1 needs two things:

- The `concern` lookup table and the `Concern` enum, since `concerns[]` is now a customer-facing
  field and the codes must be stable.
- Nullable `concern_code`, so an empty free-text box records that the detector ran and found
  nothing.

`run_id` and the de-duplication changes can wait. They matter for multi-turn sessions, and a quiz
submission is one detection run.

## Risks

**Background work on a single worker.** `render.yaml` starts one uvicorn process. A plan started
with `BackgroundTasks` dies if the process restarts mid-run, and the customer gets a permanent
`pending` and no email.

Acceptable for Phase 1 volumes, with two safeguards: mark `pending` rows older than five minutes
as `failed` on startup, and give the pipeline an explicit deadline so a hung LLM call cannot hold
a slot indefinitely. `app/services/resilience.py` already wraps calls with `safe_call` — the
deadline belongs around the whole pipeline, not each call.

**Blocking calls in an async path.** One worker means a synchronous call inside an `async def`
occupies the event loop and queues every other request behind it. Confirm the LLM and Pinecone
calls are genuinely async. `app/agents/llm_call/provider.py` is where to look.
`query_products` already uses `asyncio.to_thread` for the Pinecone call, which is the right
pattern.

**The product catalog is a hard dependency.** No catalog, no product links, no cart, no
attribution. It moved into our scope, so it is now our schedule risk rather than the supplier's.
It cannot start without a development store and a scoped Admin API token.

## Verification

1. Submit a quiz payload describing breakage. `POST` returns `202` within a second. Polling
   `GET` eventually returns `status: ready`, with `concerns: [breakage_active]`, a `you_told_us`
   quote matching the input, and a first step from `_REPAIR_MANDATORY_STEPS`.
2. Submit with `concern_text: ""`. A plan still returns, `concerns` is empty, `you_told_us` is
   null, and a detection row exists with a null `concern_code`.
3. Submit the same `submission_id` twice. One plan exists, one email is sent.
4. Close the tab immediately after submitting. The email still arrives.
5. Re-fetch a `ready` plan. The body is byte-identical.
6. Change a decision rule, then re-fetch the same `plan_id`. The plan is unchanged.
7. Every product in a plan resolves to a live Shopify product, and its `variant_id` can be added
   to a cart.
8. Post feedback, then read it back from `plan_feedback` joined to the plan.
9. Call `POST /api/plan` from a browser on the Shopify origin. No CORS error.
10. Restart the service mid-generation. The stranded plan ends as `failed`, not `pending`.
11. Run `tests/test_decision_routing.py` and `tests/qa_scenarios.py`. Routing must not change —
    this work adds a delivery format, not a new decision path.
