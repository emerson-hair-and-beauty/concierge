# Phase 1 backend plan

Status: draft 2026-09-03. Makes `PHASE1_FRONTEND_BRIEF.md` possible.

Implementation update, 2026-09-14: see [the implementation and supplier handoff](PHASE1_IMPLEMENTATION.md).
That document is the current contract and status record. Historical work items below are superseded where they conflict.

## Decisions updated 2026-09-14

This section supersedes conflicting requirements below and in the other Phase 1 documents.
These are implementation requirements, not claims that the endpoints already exist.

- The frontend supplier owns the Shopify catalog sync. We provide an authenticated catalog
  ingestion endpoint, validate each batch, and store it. Agree the batch schema and refresh
  semantics with the supplier. Preserve the last accepted catalog when a refresh fails.
- The frontend sends product click events to our events endpoint. We store them.
  The product redirect must not record a second click.
- Emerson supplies fixed step titles. One structured composer call produces the personalized
  summary, step explanations, product explanations and optional climate note together.
  Code supplies the ordered step IDs, titles and eligible product IDs. Validate the returned
  prose against those IDs and a schema before assembling the plan. The model cannot change
  the routine order or invent products.
- The existing pattern is `app/agents/orchestrator.py` -> `generateRoutine` in
  `app/agents/routine/lib/routine_prompt.py` -> `createRecommendations` in
  `app/agents/recommendation/lib/create_recommendations.py`. It requests JSON and attaches
  products per step. It does not enforce a response schema. Reuse this approach with the
  decision-state rules; do not adopt the older prompt's universal five-step routine.

### Fast failure and bounded recovery

Use these initial backend limits, then validate them with real generation timings:

- Persist an unrecoverable error immediately. Do not wait for a sweeper after a caught error.
- Give generation a 30-second deadline from acceptance, including retries and fallbacks.
  Reserve the final five seconds for validated fallback assembly and persistence.
- Set individual network timeouts within the remaining deadline. Permit at most one retry
  for transient timeouts, rate limits or service errors when sufficient time remains.
  Do not retry validation or authentication errors.
- Check abandoned jobs every five seconds and on startup. Mark pending rows older than
  35 seconds as failed. With a running service and available database, cleanup takes at
  most about 40 seconds from acceptance. A stopped service cannot report until it restarts.
- Use conditional pending-to-ready/failed writes. Late work must never replace a failed
  plan or send its email. Cancellation of a thread wait does not stop its network request.
- Record the failed stage, duration and fallback used. If persistence fails, log the error
  separately; never report that the failure status was saved when it was not.

Known failure modes and permitted fallbacks:

| Failure | Response |
|---|---|
| Empty concern text | Skip detection; use the supplied profile with no detected concerns. |
| Detection fails for nonempty text | Retry within budget, then fail. Do not treat failure as no concerns. |
| Product search fails or finds no eligible item | Keep the validated routine step without product cards; record the cause. |
| Catalog refresh fails | Keep the last accepted catalog. Check freshness before recommending products. |
| Optional climate lookup fails | Omit the climate note. Do not invent local conditions. |
| Composer times out or returns invalid schema/IDs | Use the built-in rule-based copy for the selected steps without product cards. Emerson reviews this copy before launch. |
| Email delivery fails after plan persistence | Keep the plan ready; track and retry email separately without regenerating the plan. |
| Plan cannot be persisted | Do not claim success or send a permanent link to an unsaved plan. |

Backend acceptance tests must prove immediate failure persistence, the total deadline,
abandoned-job cleanup, each fallback, and rejection of late completion. Use controlled
failures and clocks; do not depend on real provider outages. `resilience.safe_call` alone
does not enforce these requirements: it only catches synchronous exceptions.

### API route dependency

Provide a working API base URL with the mock, before frontend integration. The hostname is
open; a direct Render endpoint, including the free endpoint under consideration, is an option.
Do not require a custom domain or Shopify proxy to start. Configure CORS for the frontend
origin when it calls the backend directly. Keep the frontend base URL configurable.

If a Shopify proxy is selected, activate it before integration through that route. Only
purchase attribution can be deferred to the later attribution stage. The supplier still
needs to confirm the page-serving arrangement. Earlier example URLs are illustrative,
not a requirement to use a particular hostname or proxy.

## Context

The brief promises five endpoints, a plan by email, a permanent plan link, and a product that
the store can sell. None of the five exists today.

The engine that makes the routine does exist and works. `app/services/decision_state/` routes a
profile to a decision state, builds the routine steps, filters products and writes the prose.
The work below is a delivery layer around it, plus three gaps inside it.

Read `PHASE1_API_CONTRACT.md` first. That document assumed one blocking POST. The brief replaced
it with an async job and an email. Where the two disagree, the brief wins.

## The change that reshapes everything

`POST /api/plan` now returns `202` in well under a second, and the plan appears 10 to 20 seconds
later. The customer is told to leave the page.

That single decision creates five requirements that a blocking endpoint did not have:

1. The plan row exists before the plan does, with a `status` of its own.
2. Work continues after the response is sent.
3. A repeated submit must not start a second run or send a second email.
4. A run that dies must become `failed`, or the status page polls until 45 seconds for nothing.
5. The poll endpoint must stay fast while a plan is being generated in the same process.

Point 5 is the one that will bite. See "The blocking call problem".

---

## Work items

Ordered by what blocks the front end first.

### 1. Serve the contract as a mock, before it works

**Why first.** The supplier quotes against the endpoints and starts building. They must not wait
for the engine.

Add `app/api/plan.py` and `app/api/events.py` with the exact request and response shapes from the
brief. Return a fixed sample plan. Register both in `app/main.py`.

Ship this in week one. Every later item replaces the inside of a function whose shape is already
agreed.

### 2. Fix CORS

`app/main.py:17` sets `allow_origins=["*"]` with `allow_credentials=True`. Browsers reject that
pair, so the first real call from the store fails.

Replace the wildcard with the Emerson store origin, from an environment variable.

There is a better option, and it needs a decision from the supplier. If the browser calls
`/apps/concierge/api/...` instead of our Render domain, Shopify proxies the request server-side.
The call is then same-origin, CORS does not apply at all, and no tracking blocker sees a
third-party request. Ask for this. See "Questions for the supplier".

### 3. The tables

Four files under `sql/`, following the existing style in `sql/create_signal_events.sql`.

```sql
-- sql/create_plans.sql
CREATE TABLE IF NOT EXISTS plans (
    plan_id           UUID        PRIMARY KEY,
    submission_id     TEXT        NOT NULL UNIQUE,
    quiz_id           TEXT        NULL,
    anonymous_user_id TEXT        NOT NULL,
    email             TEXT        NULL,
    marketing_consent BOOLEAN     DEFAULT FALSE NOT NULL,
    source            TEXT        NULL,
    status            TEXT        DEFAULT 'pending' NOT NULL,
    plan_json         JSONB       NULL,
    prompt_version    TEXT        NULL,
    ruleset_version   TEXT        NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    completed_at      TIMESTAMPTZ NULL,

    CHECK (status IN ('pending', 'ready', 'failed'))
);
```

`submission_id UNIQUE` is the whole idempotency mechanism. A repeated submit hits the constraint,
and we return the existing row. No second run, no second email. Do not enforce this in
application code.

`plan_json` is written once, when the status becomes `ready`. The rules will change; a customer
who opens the link on Friday must see what they were told on Tuesday.

The other three tables:

- `sql/create_journey_events.sql` — as specified in `PHASE1_FRONTEND_TRACKING.md`.
- `sql/create_plan_feedback.sql` — one row per submission, keyed on `plan_id`. Last one wins on
  read, so keep every row and take the newest. Do not overwrite; a customer who changes their
  rating is itself a finding.
- `sql/create_catalog.sql` — see item 7.

### 4. `POST /api/plan`

1. Validate. Only `texture`, `density` and `email` are required.
2. Insert the `plans` row with `status = 'pending'`. On a `submission_id` conflict, return the
   existing `plan_id` with its current status.
3. Schedule the generation.
4. Return `202` with `{plan_id, status}`.

**Align the payload with the brief.** The quiz asks the customer for porosity directly, so the
endpoint takes it directly. Two things follow.

`OrchestratorInput` treats `porosity` as legacy and lets it override `moisture_behaviour`
silently. `app/api/models.py:14-15` says so. Do not reuse that model. Give the plan endpoint its
own request model, where `porosity` is a first-class answer and `moisture_behaviour` is a
separate optional one. If both arrive, the answer from the customer wins, and we record that it
happened.

`strand_thickness` and `elasticity` appear in the brief and in `ProfileState`, but in no input
model. Add them as optional fields.

Use FastAPI `BackgroundTasks` for step 3. Not Celery, not a queue. The work is one async
function, the volume in Phase 1 is low, and a queue adds a service to operate for no gain yet.

This choice has one real cost, and item 6 covers it.

### 5. `GET /api/plan/{plan_id}`

Reads the row. Returns `{plan_id, status}` while pending or failed, and `plan_json` when ready.
`404` on an unknown id.

This endpoint is polled every 2 seconds by every waiting customer. Keep it a single indexed
primary-key read. Do not recompute anything here.

### 6. The blocking call problem

**This is the largest technical risk in the plan.**

Uvicorn runs one worker. `app/services/db_service.py` calls the Supabase client synchronously
inside `async def` functions — `self.supabase.table(...).execute()`. A synchronous call inside a
coroutine occupies the event loop. Nothing else runs, including every status poll from every
other customer.

Today this is survivable, because the app streams to one user at a time. Under the brief it is
not: a plan generating in the background will stall the polls of everyone else.

The fix is already used elsewhere in the codebase.
`app/agents/recommendation/lib/knowledge_base/query_products.py` wraps the Pinecone call in
`await asyncio.to_thread(index.query, ...)`. Do the same for every Supabase call on the plan
path, and for the Klaviyo post in item 8.

The LLM calls are fine. `app/agents/llm_call/provider.py` uses the async clients throughout.

Verify this with load, not by reading. Measure poll latency at two levels: eight concurrent
submissions for a normal day, and twenty-five for the hour after a campaign email. The site
already carries over 10,000 visitors a month, so the spike is the realistic failure, not the
average. If a poll goes above 500 ms while a plan is generating, a synchronous call is still on
the path.

Size the model spend at the same time. Several hundred plans a month, at three LLM calls each,
is a running cost somebody should have seen before launch rather than after.

### 7. A run that dies must not poll forever

A background task lives in the process. Render restarts the process on a deploy and on an
out-of-memory condition, and the task disappears with it. The row stays `pending` for ever, the
status page polls to 45 seconds, and the email never arrives.

Add a sweeper. On startup, and every five minutes, set `status = 'failed'` on any `pending` row
older than 10 minutes. This is 15 lines and it removes a whole class of silent failure.

Record why it failed. `app/services/resilience.py` already has `record_degraded_call`.

### 8. The product data pipeline

**This moved to us.** An earlier draft gave the catalog sync to the supplier. We build it.

Today the product data is split and neither half is complete. The matrix indexer
(`index_product_matrix.py`) keys on SKU and carries the categories, hold levels and hair-type
rules that drive a recommendation, but no Shopify identifiers. `product_kb.json` keys on Handle
and carries a price and a `Type`, but no SKU. Both write to one Pinecone index, so today it is
not certain which one the live engine reads.

Build one pipeline that reads products from the Shopify Admin API and joins them to the matrix.
Unify the identifier while doing it: **one name, `shopify_id`.** The brief now uses that name
everywhere.

**Use two stores, not one.**

| Store | Holds | Changes |
|---|---|---|
| The Pinecone index | sku, category, flags, porosity, density, hold | On a matrix change |
| `catalog` table | sku, shopify_id, variant_id, handle, title, price, available | On a stock change |

Do not put `available` or `price` in the vector index. Stock moves daily, and a field in a vector
index costs a reindex to change. Query Pinecone for the semantics, then join by SKU for the rest.

```sql
-- sql/create_catalog.sql
CREATE TABLE IF NOT EXISTS catalog (
    sku         TEXT        PRIMARY KEY,
    shopify_id  TEXT        NOT NULL,
    variant_id  TEXT        NOT NULL,
    handle      TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    price       NUMERIC     NULL,
    currency    TEXT        NULL,
    available   BOOLEAN     DEFAULT TRUE NOT NULL,
    synced_at   TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
```

Run the refresh on a schedule. Handles and prices move slowly, stock moves faster, so a daily
full pass with a more frequent availability pass is the shape to aim for.

**Record every SKU with no Shopify match.** A product in the matrix with no variant is a product
we cannot sell. That list is the roadmap's "matrix gaps" item, produced for free, and Emerson
needs it.

**Guard against an empty refresh.** If a run matches fewer than half the current rows, refuse it
and alert. A broken refresh would empty the catalog, every plan would come out product-free, and
plans are permanent snapshots, so those plans could not be repaired afterwards.

We already have Shopify admin access, so this item has no external dependency. It can start now.

**Confirm which indexer is live before any of this.** If the handle-keyed source is what the
engine actually reads, the SKU join fails from the start. This is a one-hour check and it gates
the whole item.

### 9. Bind products to routine steps

A real gap in the engine, not a delivery detail.

`decision_engine.py` produces the ordered steps. `query_products` runs one semantic search for
the whole decision state and returns a flat list. Nothing says which product belongs to which
step, so `steps[].products` cannot be filled.

Item 8 makes this easier than it was. The reindex carries the matrix `category` on every record,
so the step-to-product map becomes a lookup rather than a repair job.

1. Map each step slug onto one or more categories. Do this against the reindexed vocabulary, not
   against the `Type` field in `product_kb.json`, which needs normalising and may not be live.
2. Add a `product_category` field to `ProductFilters` in
   `app/services/decision_state/models.py`, and query per step rather than once per plan.
3. Join to `catalog` by SKU and drop anything with `available = false`.

That join is what makes the promise in the brief true: we do not recommend a product the store
cannot sell.

**One supply problem to expect.** The treatment category is thin. The `repair_first` state makes
a protein treatment mandatory, so some customers will get a routine with an empty treatment step.
The brief already handles this — show the step, show no product card — but report the frequency
from week one, so Emerson can decide whether the matrix needs more products.

### 10. The step titles and the reasons

The steps are slugs today: `gentle_cleanse`, `protein_treatment`, `moisture_seal`. The brief
needs `title` and `why` on each.

Write the titles by hand, in a lookup table of about 20 entries. Do not generate them. They are
customer-facing brand copy and they must not vary between two customers with the same routine.

The `why` on each step, the `why` on each product, the `summary` and the `climate_note` come from
the model. Call `response_composer.py` for those fields, and let code place them in the envelope.
Do not ask the 928-line composer prompt to emit the whole JSON document.

### 11. Free text into the detector

`app/services/session_signal/signal_detector.py` reads a message list. A single free-text answer
is a one-message conversation, so pass it as one.

Empty text must reach `_all_clear` at line 79 and produce a plan with `concerns: []`. It must not
raise. The brief states that an empty concerns list is a valid plan, driven by profile and
climate alone.

### 12. The email

The brief says we build and send it.

`enrichment/klaviyo.py` already exists and already writes profiles, list memberships and events
against the Klaviyo API. Use it. It removes a whole dependency: no new sending service, no domain
authentication, no template system to build.

The flow: on `status = ready`, upsert the profile with the email, then fire a `curl_plan_ready`
event carrying `plan_id` and the plan link. A Klaviyo flow sends the message. Marketing consent
stays a separate property, and the plan email is transactional.

Two things to sort out first:

- The module lives in `enrichment/`, which is a scripts package. Moving it to `app/services/`
  makes it part of the application. Decide which, and do not import across the boundary.
- `_post` is synchronous. Wrap it, as item 6 requires.

### 13. `GET /apps/concierge/go`

Records the click, then redirects.

```
GET /apps/concierge/go?plan_id=<id>&shopify_id=<id>
  → insert journey_events (product_clicked)
  → 302 /products/<handle>?plan_id=<id>
```

Look up the handle from `catalog`. Validate that the `shopify_id` belongs to that plan before
redirecting, and reject anything else. An open redirect on a store domain is a real problem, not
a theoretical one.

### 14. `POST /api/events`

- Accept `text/plain` as well as `application/json`. Read the raw body and parse it. FastAPI
  will not deserialise `text/plain` into a model on its own, and the exit beacon cannot set a
  content type.
- Reject an unknown event name against the closed list in the brief.
- `ON CONFLICT (id) DO NOTHING`. The client id is the idempotency key.
- Cap at 50 events and 2 KB of props.
- Return `202` before the write completes.

**Never read events back by `quiz_id`.** The client supplies it, so anyone can send any value.
It is safe to write against and unsafe to read against.

### 15. The `orders/paid` webhook

Ours, and it needs a real Shopify app registration.

Verify the HMAC on the raw body before parsing. Read `plan_id` from `note_attributes` and
`_plan_id` from each line item. Write the join.

Respond `200` within five seconds and do the work afterwards. Shopify retries on a timeout, and
a retry that arrives while the first one is still working will double-count.

### 16. Delete `app/api/web_chat.py`

It is dead. Nothing imports it, and it would raise `ImportError` on `WebChatRequest`, which does
not exist in `app/api/models.py`. The live router is `app/web_chat_agent/router.py`. Remove the
copy so the next person does not build against it.

---

## What the brief promises, and what makes it true

| Promise in the brief | What delivers it |
|---|---|
| `202` in under a second | Item 4, the row before the work |
| The plan arrives by email | Item 12, Klaviyo |
| A double press gives one plan | Item 3, `submission_id UNIQUE` |
| The poll answers in 2 seconds | Item 6, no synchronous calls on the path |
| `failed` appears when it fails | Item 7, the sweeper |
| The link works permanently | Item 3, `plan_json` written once |
| Every product can be bought | Items 8 and 9, the catalog join |
| The porosity answer is used | Item 4, a request model of its own |
| Incomplete data is normal | Item 10, per-field `safe_call` |
| A closed event vocabulary | Item 14 |
| Purchases attributed to a plan | Item 15 |

---

## Questions for the supplier

1. **Where do the pages actually live?** The brief gives the plan page as
   `/apps/concierge/plan/{plan_id}`, but an app proxy forwards that path to us, and we would
   then have to serve the page. The brief says they build it. Either the proxy returns Liquid
   that the theme renders, or the page is a normal Shopify template and the proxy only covers
   `/go`. This changes who builds the page, so settle it before anyone quotes.
2. **Will the browser call `/apps/concierge/api/...` rather than our Render domain?** If yes,
   CORS disappears and no request is third-party. We prefer this.
3. **Who sets up the app proxy?** We have Shopify admin access, which covers the Admin API
   token, the `orders/paid` webhook and a custom pixel. It does not cover an app proxy. A proxy
   needs a real app, configured outside the admin. This is the only Shopify access question left,
   and the proxy is what keeps every call first-party.

## Open, and not yet answered by anyone

**The brief went out with the catalog sync in the supplier's scope.** We build it now. Tell them
before they quote, or the quote carries work we will not use.

**The 10 to 20 second figure in the brief has never been measured.** The supplier designs three
things around it: the "wait approximately 20 seconds" copy, the 45-second poll stop, and the
2-second interval. If the real figure is 40 seconds, the status page is wrong and gets rebuilt.

Time ten real generations before the brief goes out. This is the cheapest item on the plan, and
the one most likely to cause rework.

## Verification

1. Submit a quiz. `202` returns in under a second, with a `plan_id` and `status: pending`.
2. Submit the identical payload twice with one `submission_id`. One `plans` row exists, one
   email is sent, and both calls return the same `plan_id`.
3. Poll while a plan is generating. Every poll answers in under 500 ms.
4. Run eight concurrent submissions with continuous polling, then twenty-five. No poll exceeds
   500 ms in either. This is the test for item 6 and it is the one worth automating.
5. Kill the process mid-generation, then restart. Within 10 minutes the row reads `failed`, and
   the status page shows the failure state.
6. Submit with `concern_text: ""`. A plan returns, `concerns` is empty, `you_told_us` is null.
7. Submit `porosity` and `moisture_behaviour` together. The porosity answer is the one used,
   and the conflict is recorded.
8. Confirm which indexer populated the live Pinecone index. The SKU join depends on it.
7. Submit with text describing breakage. `concerns` carries `breakage_active`, and the first step
   comes from `_REPAIR_MANDATORY_STEPS`.
8. Mark a SKU unavailable, then generate a plan that would have chosen it. It does not appear.
9. Change a decision rule, then re-fetch an existing `plan_id`. The body is unchanged.
10. Run a catalog refresh that matches under half the rows. It is refused.
11. Call `/apps/concierge/go` with a `shopify_id` that is not in that plan. It is refused.
12. Buy a recommended product. The `orders/paid` payload carries `plan_id` in `note_attributes`
    and `_plan_id` on the line, and the join row exists.
13. Run `tests/test_decision_routing.py` and `tests/qa_scenarios.py`. Routing must not change.
    This work adds a delivery format, not a new decision path.
