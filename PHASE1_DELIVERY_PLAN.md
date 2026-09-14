# Phase 1 delivery plan

Status: draft 2026-09-03. Sits above the brief and the backend plan.

Implementation update, 2026-09-14: [the implementation and supplier handoff](PHASE1_IMPLEMENTATION.md)
is the current contract and status record. The supplier owns catalog sync and sends it to our ingestion endpoint.
The route is available with the Stage 1 mock. A direct Render URL is supported; no proxy is required to start.
Historical ownership, endpoint, explanation and timeout requirements below yield to that document.

## What this document is

The roadmap says what Phase 1 is. The brief says what the supplier builds. The backend plan says
what we build. None of the three says in what order, or who waits for whom.

This document answers that. It carries no new requirements.

**No dates.** The sequence below is expressed as dependencies, not as a calendar. Put dates on it
once the supplier quotes and Emerson confirms when the designs and the questions arrive.

## The document set

| Document | Audience | Answers |
|---|---|---|
| `Curl_Concierge_Phased_Product_Roadmap.pdf` | Emerson | Why this, and what comes after Phase 1 |
| `PHASE1_FRONTEND_BRIEF.md` | The supplier | What they build, and every endpoint they call |
| `PHASE1_FRONTEND_TRACKING.md` | The supplier | What the pages report, and how |
| `PHASE1_API_CONTRACT.md` | Us | The plan shape and how it is assembled |
| `PHASE1_BACKEND_PLAN.md` | Us | The sixteen items we build |
| This document | Everyone | The order, and who waits for whom |

Where the brief and the contract disagree, the brief wins. The contract assumed one blocking
POST. The brief replaced it with an async job and an email.

## The three parties

| Party | Owns |
|---|---|
| Emerson | The designs, the quiz questions, the brand copy, the product matrix, the curators |
| The supplier | The pages, the app proxy, the tracking calls, the pixel |
| Us | The API, the engine, the plan record, the product catalog, the email trigger, the order webhook |

The boundary that matters: **the supplier writes to our API and never to our database.** Every
cross-team failure in a project like this comes from a second write path.

---

## The sequence

### Stage 0 — Unblock

Nothing else starts cleanly until these four are settled. All four are decisions, not code.

1. **Where the plan page lives.** The brief gives `/apps/concierge/plan/{plan_id}`, but an app
   proxy forwards that path to us, which would make the page ours to serve. Either the proxy
   returns Liquid for the theme to render, or the page is a Shopify template and the proxy only
   covers `/go`. This changes what the supplier is quoting.
2. **Make the API route available early.** Supply a working base URL with the Stage 1 mock,
   before frontend integration. The hostname is open. A direct Render endpoint is an option,
   including the free endpoint under consideration. No custom domain or Shopify proxy is
   required to start. For direct calls, configure CORS for the frontend origin.
3. **Assign route setup.** We supply the backend endpoint. The supplier configures the
   frontend base URL. If a Shopify proxy is chosen, assign its setup and activate it before
   integration through that route. The page-serving arrangement remains a separate decision.
4. **Give the supplier the catalog endpoint contract.** They have quoted the sync and own it.
   We validate and store their catalog through `POST /api/catalog`.

Emerson also has to start on the designs and the quiz questions here. They gate the supplier, and
they are the item most likely to slip, because they are creative work rather than engineering.

### Stage 1 — Build in parallel

Two tracks that do not touch each other. This is the point of item 1 in the backend plan.

**We ship the mock first.** `POST /api/plan`, `GET /api/plan/{plan_id}`, `POST /api/events` and
the feedback endpoint, returning the exact shapes from the brief with a fixed sample plan. The
supplier then builds every page without waiting for the engine.

The mock must be reachable through the agreed initial route at this stage. Keep the API base
URL configurable so a later hostname change does not require changes to the page logic.

| Our track | Their track |
|---|---|
| Mock endpoints, then the real tables | The quiz page against the mock |
| Step-to-title lookup, step-to-product binding | The status page and its poll |
| `Type` normalisation in the product matrix | The plan page from the designs |
| The product data pipeline and the catalog table | The tracking calls |
| The free-text path into the detector | |
| The `asyncio.to_thread` work | |

Our engine work has no external dependency at all. It can start on day one and it should, because
it is the part with unknown depth. The step-to-product binding is a genuine gap in the engine, not
a delivery detail.

### Stage 2 — Join

The mock retires. Real plans start returning.

This stage needs both tracks to have landed, and it needs the product catalog to have run once. The
order inside it:

1. The catalog pipeline runs and reports its unmatched SKUs.
2. Emerson reviews that list. A SKU with no Shopify variant is a product we cannot sell.
3. The engine joins to the catalog and starts dropping unavailable products.
4. The mock is switched off, one endpoint at a time.
5. The email fires through Klaviyo for the first time.

**Do not switch off the mock before the catalog has run.** A real plan with no product data is
worse than a fixed sample, because it looks correct.

One check comes before all of this, and it takes an hour. Two product sources exist today and
both write to one Pinecone index: a SKU-keyed matrix and a handle-keyed export. Confirm which
one the live engine reads. If it is the handle-keyed one, the SKU join fails from the start.

### Stage 3 — Attribution

Everything after the plan page. None of it blocks the launch of the diagnostic itself, which is
why it comes last.

- Reuse the API route established in Stage 1; route setup does not wait for attribution.
- `/apps/concierge/go` records clicks and redirects.
- The cart attribute and the line item property are stamped on add.
- The web pixel reports add-to-cart and checkout.
- Our `orders/paid` webhook writes the join.

This stage can slip a week without stopping customers from getting plans. Say so out loud when
the schedule tightens, because it is the obvious thing to cut and the cut is survivable.

### Stage 4 — Launch readiness

Five things, and none of them is optional.

1. **The concurrency test.** Eight simultaneous submissions with continuous polling. No poll over
   500 ms. This is the test for the single-worker blocking problem, and it is the failure most
   likely to reach customers.
2. **The sweeper.** Kill the process mid-generation and confirm the row becomes `failed`.
3. **The consent path.** Confirm the pages send nothing when `Shopify.customerPrivacy` refuses,
   and that the quiz still works.
4. **The empty-state pass.** Walk every row of the brief's empty-field table on a real device.
5. **Placement.** The site already receives over 10,000 visitors a month, so the question is
   where the quiz sits, not how to attract an audience. Navigation, homepage and product pages
   are worth roughly five times a single buried link. This is Emerson's work, it has no
   dependency on anything above, and it should be settled in Stage 0.

---

## The critical path

Four items gate more than themselves. Watch these and the rest follows.

| Item | Owner | Gates |
|---|---|---|
| The quiz questions and permitted answers | Emerson | The whole supplier track |
| The step-to-product binding | Us | Every real plan |
| The product data pipeline | Us | Product cards, and the availability promise |
| The working API route | Us and the supplier, see Stage 0 | Frontend integration; proxy setup only if selected |

The product data pipeline is the riskiest of the four, and it is now ours. Its failure is silent:
a run that empties the catalog produces plans with no products, and plans are permanent
snapshots, so those plans cannot be repaired afterwards. The refusal guard in the backend plan
exists for this.

It has no external dependency. We hold Shopify admin access already, so the pipeline can start
now, and it should. It is the item with the least certain depth.

## What Emerson owes, and when

| Item | Needed by |
|---|---|
| The quiz questions, their order, and each permitted answer | Stage 1, or the supplier stops |
| The designs for four pages | Stage 1 |
| The step titles and their one-line reasons | Stage 1, for our lookup table |
| The WhatsApp number and its prepared message | Stage 2 |
| The privacy policy link | Stage 2 |
| Klaviyo access | Stage 0 |
| The traffic and launch plan | Before launch |

The step titles are easy to forget. They are brand copy, not engineering, and they must not vary
between two customers with the same routine, so they cannot be generated.

## Decision gates

**Before Stage 2 closes.** Read 20 generated plans against the products they recommend. If the
step-to-product binding is picking the wrong things, that is cheaper to find now than after
launch.

**The first 50 to 100 completed plans.** At the expected volume this arrives two to four weeks
after launch, so book the curator time before launch rather than after. The roadmap's manual
quality review. Emerson compares
the engine's output with what a curator would have said. This is the gate that decides whether
Phase 1.5 starts, and it needs a date set before launch, not after.

**Before Phase 2 is scoped.** The roadmap lists the evidence required: demand, a credible
completion rate, acceptable accuracy, product engagement, and return use. The tracking built in
Phase 1 is what produces it. Nothing in Phase 1 should be cut in a way that removes that
evidence.

## Risks

| Risk | Owner | What we do |
|---|---|---|
| The single worker stalls under load | Us | The concurrency test in Stage 4, before launch |
| A dead background task polls for ever | Us | The sweeper |
| The catalog run empties the catalog | Us | Refuse a run matching under half the rows |
| The live index is the handle-keyed one | Us | Confirm before Stage 2. The SKU join depends on it |
| The 10 to 20 second figure is wrong | Us | Time ten runs before the brief goes out |
| Too few products of type Treatment | Emerson | Report the frequency of empty steps from week one |
| The designs or questions slip | Emerson | The mock keeps the supplier moving, but only for pages |
| Scope grows into a rebuild | Everyone | The brief's "not in this phase" list is the answer |
| The quiz is hard to find | Emerson | The site already carries 10,000 visitors a month. Placement decides the volume, so settle it in Stage 0 |

The last one is the roadmap's own first risk, and it is the only one on this list that engineering
cannot fix.

## Definition of done

Phase 1 is complete when a customer can:

- find the diagnostic on the Emerson site;
- complete it without leaving;
- receive a plan by email, and read it on a permanent link;
- buy the recommended products;
- ask a curator for help on WhatsApp;
- rate the plan.

And when Emerson can answer, from data and without asking engineering:

- how many people start, and how many finish;
- where the others stop;
- how long it takes;
- which recommendations get clicked, added and bought;
- which plans customers say are wrong.

## Not in Phase 1

From the roadmap, repeated here so it is in the same place as the schedule:

- Customer accounts, a login, or a dashboard.
- The conversational chat agent.
- Automated WhatsApp plan delivery.
- Win-back campaigns and behavioural segments. These are Phase 1.5.
- Long-term routine tracking, camera analysis, and the mobile app.

Plans that follow a customer across devices are also excluded. Nothing is stored on the device,
so the plan link is the only thread. That is a deliberate trade, and it is what keeps the pages
free of storage consent.
