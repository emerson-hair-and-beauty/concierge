# Phase 1 front-end tracking guide

Status: draft 2026-09-03. Pairs with `PHASE1_API_CONTRACT.md`.

Implementation update, 2026-09-14: [the current supplier handoff](PHASE1_IMPLEMENTATION.md)
supersedes conflicting event and transport details below. The frontend owns product-click events;
the backend stores them. Redirects do not record another click. `email_save_submitted` is removed.
The pixel's `product_added_to_cart` and `checkout_completed` are accepted by `/api/events`.
The API base URL is configurable, and a direct Render endpoint is supported.

## Context

`PHASE1_API_CONTRACT.md` settles the plan. It does not settle the journey to the plan, or what
the customer does after it.

`POST /api/plan` writes a row only when a plan is generated, so a table of plans is a table of
completions. The roadmap also asks for diagnostic starts, abandonment points, time to
completion, product clicks, WhatsApp requests and purchases. This guide adds the event stream
that carries them.

There is no login. Nothing is stored on the customer's device.

## The two ids

Everything rests on these. There are no others.

| Id | Minted | Lives | Covers |
|---|---|---|---|
| `quiz_id` | Client, at question one | A variable in the page | Starts, abandonment, time to completion |
| `plan_id` | Server, at plan creation | The URL, the cart, the order | Everything after the plan |

`quiz_id` is a plain variable. Do not put it in `localStorage`, a cookie, or `sessionStorage`.
The quiz happens in one sitting, so an id that dies with the tab is enough. That keeps the app
free of device storage, which removes the private-window handling, the Safari storage limits and
a consent question.

`plan_id` is the durable one. It already travels the whole way on its own:

```
plan page URL  →  product link  →  cart attribute  →  order
```

`POST /api/plan` carries the `quiz_id`, and the server stores it on the `plans` row. That single
column joins the two halves, so the funnel reads end to end.

### What this cannot do

A visitor who returns cold, with no link, is a new visitor. If they arrive through their plan
link then `plan_id` is in the URL and you know them. If they type the store address fresh, you
do not. Recognising that person needs device storage, and Phase 1 does not.

## Change required to the contract

One column, and it is smaller than it looks.

- `POST /api/plan` accepts an optional `quiz_id`.
- The `plans` table gains a `quiz_id TEXT NULL` column.

`anonymous_user_id` stays exactly as the contract describes it. The server still mints it per
submission, because `signal_events` and `decision_state_events` need a non-null `user_id`. It is
no longer a front-end concern.

## What the front end builds

One module, then call sites. Paste this in and stop thinking about transport.

```js
const tracker = {
  q: [],
  quiz_id: null,
  plan_id: null,

  init() {
    this.quiz_id = crypto.randomUUID();
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') this.flush(true);
    });
    setInterval(() => this.flush(false), 5000);
  },

  track(name, props = {}) {
    this.q.push({
      id: crypto.randomUUID(),
      name,
      occurred_at: new Date().toISOString(),
      props,
    });
    if (this.q.length >= 20) this.flush(false);
  },

  flush(leaving) {
    if (!this.q.length) return;
    const body = JSON.stringify({
      quiz_id: this.quiz_id,
      plan_id: this.plan_id,
      events: this.q.splice(0),
    });
    if (leaving) {
      navigator.sendBeacon(EVENTS_URL, new Blob([body], { type: 'text/plain' }));
    } else {
      fetch(EVENTS_URL, { method: 'POST', body, keepalive: true }).catch(() => {});
    }
  },
};
```

On the plan page, set `tracker.plan_id` from the URL before the first `track` call. On the quiz
page, `plan_id` stays null until the plan comes back.

Everything after this is one line per moment:

```js
tracker.track('quiz_step_answered', { step_index: 3, question_id: 'porosity' });
```

## The envelope

Sent once per flush, not once per event.

```json
{
  "quiz_id": "b120...",
  "plan_id": null,
  "events": [
    {
      "id": "0a91...",
      "name": "quiz_step_answered",
      "occurred_at": "2026-09-03T10:12:04.221Z",
      "props": {"step_index": 3, "question_id": "porosity"}
    }
  ]
}
```

At least one of `quiz_id` and `plan_id` must be present. Both are present on the plan page when
the customer reaches it in the same sitting.

## Event vocabulary

The client sends only what the browser alone knows. The vocabulary is closed.

| Name | When | props |
|---|---|---|
| `quiz_started` | The first question renders | `referrer`, `utm`, `entry_path` |
| `quiz_step_viewed` | Each question renders | `step_index`, `question_id` |
| `quiz_step_answered` | An answer is accepted | `step_index`, `question_id` |
| `quiz_submitted` | The customer presses submit | `step_count`, `free_text_used` |
| `plan_viewed` | The results page renders | `revisit` (true or false) |
| `plan_step_expanded` | A routine step is opened | `step` |
| `product_clicked` | A product link is pressed | `shopify_id`, `step` |
| `whatsapp_requested` | The WhatsApp button is pressed | `step`, `origin` |
| `email_save_submitted` | The email form is sent | `marketing_consent` |
| `feedback_submitted` | The rating is sent | `rating` |
| `plan_exited` | The page hides | `dwell_ms`, `deepest_step` |

## What the client must not send

Four measures belong to the server. If the client also reports them, the two disagree, and the
weaker number is the one somebody quotes.

- **`plan_generated`** — the `plans` row is the record. Derive it.
- **Abandonment** — do not emit `quiz_abandoned`. A browser that closes cannot report reliably.
  Derive it: a `quiz_id` with a `quiz_started` and no `quiz_submitted` after 30 minutes is an
  abandonment, and its highest `step_index` is the abandonment point.
- **Time to completion** — derive it from `quiz_started` to `quiz_submitted`. Report the median,
  and trim the sessions that idle. One customer who leaves a tab open all day moves the mean.
- **Purchases** — the `orders/paid` webhook is the record.

## Server side

### The table

```sql
-- sql/create_journey_events.sql
CREATE TABLE IF NOT EXISTS journey_events (
    id          UUID        PRIMARY KEY,
    quiz_id     TEXT        NULL,
    plan_id     UUID        NULL REFERENCES plans (plan_id),
    name        TEXT        NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    props       JSONB       DEFAULT '{}'::jsonb NOT NULL,

    CHECK (quiz_id IS NOT NULL OR plan_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_journey_events_quiz ON journey_events (quiz_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_journey_events_plan ON journey_events (plan_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_journey_events_name ON journey_events (name, occurred_at);
```

Three decisions in that shape:

- **The client supplies `id`.** It is the idempotency key. A retried batch inserts nothing new,
  so a flaky connection cannot inflate the counts. Use `ON CONFLICT (id) DO NOTHING`.
- **Two timestamps.** `occurred_at` is the browser clock and can be wrong. `received_at` is the
  server clock. Report on `occurred_at`, and use `received_at` to find skew and late arrivals.
- **`props` is JSONB.** Promote a field to a column once you query it every week.

### `POST /api/events`

Takes the envelope above. Returns `202` with no body.

- Reject an unknown `name`. A typo must fail loudly, not create a silent event type nobody
  counts.
- Cap the batch at 50 events and `props` at 2 KB.
- Never block the response on the write. This endpoint must not slow the quiz.
- Accept `text/plain` as well as `application/json`. See the beacon note below.
- The same CORS problem as the contract applies. Fix `allow_origins` in `app/main.py` first.

**Never read events back by `quiz_id`.** It is a client-supplied value, so anyone can send any
value they like. It is safe to write against and unsafe to read against. `plan_id` is the only
readable key, because the server mints it and it is unguessable.

## Reliability details that decide whether the numbers are real

**Use `visibilitychange`, not `beforeunload`.** Mobile Safari often skips `beforeunload`, which
is exactly where abandonment happens most. Send the exit batch when
`document.visibilityState` turns `hidden`.

**Use `navigator.sendBeacon` for that exit batch.** A normal `fetch` is cancelled when the page
goes away. Beacon cannot set headers, and a JSON content type forces a preflight the browser
will not run at that moment. Send a `Blob` with type `text/plain`, and parse the body on the
server.

**Queue and flush.** Flush every 5 seconds, or at 20 events, and always flush on hide. Never
send one request per keystroke.

**Fail silent, on the customer's side only.** A tracking failure must never block a question, a
submit, or a product link. Log it and continue.

## The Shopify layer

The quiz and the plan page report themselves. The cart and the purchase belong to Shopify. Four
native pieces cover those, with no third-party analytics tool.

**1. App proxy.** Serve the plan page under `/apps/concierge` so it runs on the store domain.
This keeps the calls first-party, which survives the tracking blockers that break a cross-domain
request.

**2. Product links through your own endpoint.** Log the click on the server, then redirect.

```
/apps/concierge/go?plan_id=<id>&shopify_id=<id>
  → write journey_events → 302 /products/<handle>?plan_id=<id>
```

Log before you redirect. A click that leaves the page cannot report afterwards.

**3. Cart attributes and line item properties.** Stamp the plan on the cart when the customer
adds a recommended product.

```js
POST /cart/update.js  { "attributes": { "plan_id": "<id>" } }
POST /cart/add.js     { "id": <variant>, "properties": { "_plan_id": "<id>" } }
```

The attribute reaches `order.note_attributes`. The property reaches the order line, which gives
attribution per product. Re-stamp on every add, because a cleared cart drops the attribute.

**4. Web pixel extension and the `orders/paid` webhook.** The pixel reports
`product_added_to_cart` and `checkout_completed`. The webhook is the record of truth for a
purchase. Read `note_attributes` and the line properties there, then write the join to the
database.

The pixel runs in a sandbox and cannot see the page's variables. `plan_id` on the cart is the
only bridge between your page and the order. Keep it there.

**Every outbound link must carry `plan_id`.** The customer takes the quiz on Monday and buys on
the following Wednesday. Nothing is stored on their device, so the link is the only thing that
still connects the two. This makes the plan link the retention mechanism, not a convenience.

## Consent

Gate every event on `Shopify.customerPrivacy` before the first send. In some regions nothing may
fire, and the funnel must degrade to fewer numbers rather than to an error.

The email is personal data. Capturing it moves the app into Shopify's protected customer data
approval. Keep `marketing_consent` separate from plan delivery, as the roadmap requires.

## Verification

1. Start the quiz, answer two questions, then close the tab. A `quiz_started`, two
   `quiz_step_answered` and a `plan_exited` row exist, all sharing one `quiz_id`.
2. Replay the same batch twice. The row count does not change.
3. Complete a quiz. The `plans` row carries the same `quiz_id` as the earlier events.
4. Post an event with `name: "typo_event"`. The endpoint returns an error and writes nothing.
5. Abandon a quiz, wait past the window, then run the abandonment query. It appears, with the
   correct deepest `step_index`.
6. Open a plan link in a fresh browser. `plan_viewed` records against the right `plan_id`, with
   no `quiz_id`.
7. Click a product from the plan page. A `product_clicked` row exists, and the redirect lands on
   the product with `plan_id` in the URL.
8. Add that product to the cart and buy it. The `orders/paid` payload carries `plan_id` in
   `note_attributes` and `_plan_id` on the line.
9. Run the quiz with `localStorage` disabled. Everything works, because nothing uses it.
