# Phase 1 implementation and supplier handoff

Updated 2026-09-14. This document supersedes conflicting requirements in the earlier plans.

The backend is implemented locally. It has not been deployed or connected to a working Phase 1 database.
The supplier owns the pages and Shopify catalog sync. Emerson owns the designs, questions and brand review.

## Run the early integration API

Use Python 3.11 or newer. Install `requirements-phase1.txt`.

```powershell
$env:PLAN_MODE = 'mock'
$env:CORS_ALLOWED_ORIGINS = 'https://your-store.myshopify.com'
python -m uvicorn app.phase1_main:app --host 127.0.0.1 --port 8000
```

`/docs` exposes the request schemas. `/openapi.json` supplies the machine-readable contract.
`/api/phase1/health` reports the selected mode and missing configuration names.
`render.phase1.yaml` defines a separate mock service for early frontend integration.
The hostname is open. A direct Render endpoint is supported; no Shopify proxy is required.
Set the frontend API base URL in configuration. Allow its exact origin through `CORS_ALLOWED_ORIGINS`.

The free Render blueprint is for early integration. Free services sleep after 15 idle minutes and can take about a minute to restart.
The backend deadline starts after acceptance; it cannot limit platform startup time.
Confirm hosting before promising subsecond submission responses to customers. See [Render's free-service behaviour](https://render.com/docs/free).

Mock mode returns a fixed routine with a sample product card and an empty product step.
It sends no email and stores nothing permanently. Records disappear when the mock restarts.
Do not launch the customer quiz against mock mode. Sample Shopify IDs cannot be purchased.
The mock is limited to 1,000 submissions per process.

## Supplier contract

All paths below are relative to the configurable backend base URL.

| Method and path | Result |
|---|---|
| `POST /api/plan` | `202` with `plan_id` and `status` |
| `GET /api/plan/{plan_id}` | Pending/failed status, or the frozen ready plan; unknown IDs return `404` |
| `POST /api/plan/{plan_id}/feedback` | `202`; every submission is retained, latest rating wins in reports |
| `POST /api/events` | `202`; accepts JSON or a `text/plain` JSON beacon |
| `POST /api/catalog` | Authenticated, atomic catalog import; returns an acceptance report |
| `GET /api/plan/{plan_id}/go?shopify_id=...` | Validates membership and redirects; does not record clicks |
| `POST /api/webhooks/shopify/orders-paid` | Backend-owned Shopify webhook; verifies the raw-body HMAC |

The older `/apps/concierge/go` redirect remains an alias. It does not require using that URL.
The supplier serves the plan page; this API does not serve the customer-facing page.
Set `PLAN_PUBLIC_URL_TEMPLATE` to that page before enabling email delivery.
The optional resend endpoint from the old API document is not part of this release.

### Submit

```json
{
  "submission_id": "8073d23f-055d-4f28-9e61-c3dc9fef878b",
  "quiz_id": "30d6d62b-f23e-4b42-b7ba-805a67ad79e5",
  "texture": "3B",
  "density": "medium",
  "porosity": "low",
  "concern_text": "My curls drop by noon.",
  "email": "customer@example.com",
  "marketing_consent": false,
  "source": "shopify_quiz"
}
```

`submission_id`, `texture`, `density`, and `email` are required.
Mint a UUID once per attempt. Reuse it for every retry, including network failures.
The database unique constraint ensures one generation and one initial delivery record.
Optional fields and permitted values are in `/docs`. Free text is limited to 1,000 characters.
An explicit porosity answer wins over moisture behaviour; the backend records that precedence.
Missing porosity stays unknown. It is not silently converted to medium porosity.

Poll every two seconds. A known failure appears immediately when it can be persisted.
Stop polling at 45 seconds as a browser safeguard, and preserve the customer's next actions.
The service accepts at most 25 simultaneous generations per worker. A busy service returns `429` with `Retry-After`.
Do not discard the answers on `429`, `422`, or a failed submit.

### Catalog ingestion

The supplier calls this endpoint from their server or sync job, never from customer JavaScript.
Send `Authorization: Bearer <CATALOG_INGEST_TOKEN>` and `Content-Type: application/json`.

```json
{
  "sync_id": "b4618698-66c6-4cf5-9489-1b2a97e0f1d5",
  "generated_at": "2026-09-14T12:00:00Z",
  "mode": "full",
  "products": [{
    "sku": "EM-CL-200",
    "shopify_id": "7412000",
    "variant_id": "41988000",
    "handle": "hydrating-cleanser",
    "title": "Hydrating Cleanser",
    "price": "89.00",
    "currency": "AED",
    "available": true
  }],
  "unmatched_matrix_skus": []
}
```

- Send numeric Shopify IDs as strings. Use `shopify_id`, not `product_id`.
- One SKU must identify one purchasable variant. Duplicate SKUs in a batch are rejected.
- `full` means one complete snapshot, not one pagination page. Collect all pages before posting.
- A full snapshot marks omitted products unavailable. It never deletes historical plan data.
- `partial` updates only the supplied SKUs. It still requires complete fields for each supplied product.
- Include matrix SKUs without Shopify matches in `unmatched_matrix_skus`.
- Use a new `sync_id` for each refresh. An identical retry returns the previous report.
- Reusing a sync ID with changed data, or sending an older refresh, returns `409`.
- Refreshes older than 24 hours or more than five minutes in the future are rejected.
- A full refresh matching fewer than half the stored SKUs is refused atomically.
- Limits: 2,000 products and 2 MB per request. Agree a different protocol before exceeding these limits.
- Current recommendation eligibility requires catalog data less than 24 hours old.

The supplier should schedule full refreshes daily and availability updates more frequently.
The backend stores the last accepted catalog when an import fails.
The import response includes `sync_id`, `accepted`, `matched_existing`, and `unmatched_matrix_skus`.

### Tracking and purchases

The frontend owns `product_clicked`. Send it once to `/api/events` with `plan_id`, `shopify_id`, and `step`.
The redirect does not create a second event. A direct product link may also carry `plan_id`.
Re-stamp the cart attribute `plan_id` and line property `_plan_id` on each recommended add.

The closed event list is:

`quiz_started`, `quiz_step_viewed`, `quiz_step_answered`, `quiz_submitted`, `plan_viewed`,
`plan_step_expanded`, `product_clicked`, `whatsapp_requested`, `feedback_submitted`,
`plan_exited`, `product_added_to_cart`, and `checkout_completed`.

The last two events come from the supplier's Shopify pixel.
Do not send `email_save_submitted`, `plan_generated`, `quiz_abandoned`, or purchase-truth events.
Paid-order webhooks are the authoritative purchase source.
Event UUIDs are idempotency keys. Limits are 50 events per batch and 2 KB per props object.
Consent gates remain the supplier's responsibility. Refused analytics consent must not block the quiz.
Do not store quiz identifiers or answers in cookies, localStorage, or sessionStorage.
No public endpoint reads events by `quiz_id`.

## Backend behaviour

- The existing decision engine chooses the routine. Its routing code is unchanged.
- Fixed titles come from a lookup. One composer call writes all personalized prose in a validated JSON schema.
- Code verifies every returned step ID and product SKU. The model cannot change order or add products.
- Search is per routine step and read-only. The legacy index initializer is not used.
- Category and product constraints are hard checks. Unsupported required flags are not silently ignored.
- Catalog freshness and availability are checked before a product enters a plan.
- Completed plans are immutable database snapshots. Changes to rules, prices, or stock do not rewrite them.
- Empty concern text skips the detector and stores a detection record with a null concern code.
- Nonempty-text detection failure cannot masquerade as a successful all-clear result.
- Generation gets 25 seconds, with up to five more seconds for persistence. Completion after 30 seconds is rejected in SQL.
- Caught fatal failures are persisted immediately. A five-second sweeper marks interrupted jobs older than 35 seconds failed.
- A stopped service cannot run a sweeper; it checks again on startup.
- Product or climate failures remove the affected optional content, with diagnostics.
- Composer failures use built-in rule-based prose and omit product cards. Emerson should review this copy before launch.
- Email has a durable outbox with leases and five attempts. Email failure does not fail or regenerate a ready plan.
- The Klaviyo event has a stable unique ID. Configure a transactional `curl_plan_ready` flow using `plan_url`.
- Outbox `sent` means Klaviyo accepted the event, not confirmation that the inbox received the message.
- Marketing consent is carried separately. This code does not subscribe customers to marketing lists.
- The paid-order webhook saves minimal attribution data before acknowledging, so a restart cannot lose an acknowledged order.

## Database and launch

1. Apply `sql/create_phase1.sql` through a privileged database connection.
2. Configure the live values in `PHASE1_ENV.example`. Use a Supabase service-role key, never a browser key.
3. Set up the supplier's catalog job and verify a complete import and its unmatched SKU report.
4. Confirm indexed metadata covers the required categories and flags. Missing evidence can produce empty product steps.
5. Configure the supplier's page URL, CORS origins, and Klaviyo transactional flow.
6. Set `PLAN_MODE=live`. For the existing app, also set `PHASE1_ENABLED=true`.
7. Run the real database, catalog, email, Shopify purchase and load checks before customer launch.

Private database views support operations: `phase1_plan_summary`, `phase1_quiz_funnel`,
`phase1_latest_feedback`, and `phase1_order_attribution`.
The attribution view rejects unknown plan IDs and line items absent from the referenced recommendation.
`plan_email_outbox` shows delivery failures. `catalog_syncs` preserves import results.

## Verification and remaining external work

```powershell
python -m unittest tests.test_phase1 tests.test_decision_routing -v
npm ci --prefix tests/sql
npm test --prefix tests/sql
python scripts/phase1_preflight.py
python scripts/phase1_load_check.py
```

The first two suites use no live services. SQL tests execute the migration in PGlite PostgreSQL.
`scripts/phase1_generation_check.py` runs ten synthetic generations with live models and read-only search.
It uses an empty catalog and sends no email. Its results cannot certify catalog joins or complete delivery latency.

Recorded checks:

- 52 offline Python tests passed, including the 26 existing decision-rule tests.
- 35 local SQL checks passed.
- Ten revised live-model runs returned valid plans in 8.5-12.6 seconds.
- Loopback HTTP tests passed with 8 and 25 simultaneous submissions. Maximum polling latency was about 40 ms.
- The separate existing live chat routing QA passed 27 of 30 scenarios. This suite does not use the new plan generator.

The chat QA mismatches were `06 Overwhelmed by products`, `07 New to curly hair routine`, and
`27 4C moisture retention general`. The result file records the expected and actual states.
Those detector/intent expectations remain unresolved. The underlying decision rules were not changed for this release.
Evidence is in `tests/phase1_generation_results.json`, `tests/phase1_load_results.json`, and
`tests/phase1_legacy_qa_results.json`. A static supplier schema is in `tests/phase1_openapi.json`.

An expanded live query returned 247 SKU-based records; 130 had a populated category and 117 did not.
There was one record in the Treatment category. Several required engine flags are absent from the index vocabulary.
See `PHASE1_MATRIX_GAPS.md`. These gaps can prevent product recommendations even after the Shopify catalog arrives.
The configured Supabase hostname was unreachable during implementation.
Render deployment access, Klaviyo credentials, a supplier page URL, and a webhook secret were not available.
The database migration, hosted route, email flow, supplier pages and real purchase test remain external launch work.

Technical references: [PostgREST writes](https://docs.postgrest.org/en/stable/references/api/tables_views.html),
[Pinecone query](https://docs.pinecone.io/reference/api/2025-10/data-plane/query),
[Klaviyo event deduplication](https://developers.klaviyo.com/en/reference/events_api_overview),
[PGlite SQL tests](https://pglite.dev/docs/).
