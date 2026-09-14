# Curl Concierge — front-end brief

Status: draft 2026-09-03. We wrote this brief for a front-end developer to quote from.

Implementation update, 2026-09-14: use [the current supplier handoff](PHASE1_IMPLEMENTATION.md)
for the implemented endpoint contract. The supplier owns catalog sync and product-click events.
Send the catalog to `POST /api/catalog`; send clicks to `POST /api/events` exactly once.
The redirect does not record another click. API and page hostnames remain configurable.
The updated handoff supersedes conflicting transport, event and catalog details below.

This document is complete. It gives each endpoint, each request, and each response that you
need. You need no other document.

## What we build

We have a diagnostic engine. The engine reads the hair profile of a customer. It then makes a
routine and selects products from the Emerson store.

The quiz that supplies the engine is difficult to find today. Few customers use it. This project
puts a new quiz on the Emerson website. The quiz sends the answers to our API. We then send the
customer a personal routine by email, with the products that suit their hair.

The customer does not make an account. There is no login in this journey.

## Scope

### You build

- The quiz page and its questions.
- The status page.
- The plan page, from designs that we supply.
- The feedback step.
- The tracking, the cart attribution, and the Shopify web pixel.
- The consent and the privacy controls on the quiz page.
- **The Shopify catalog sync.** Refer to its own section below. This is the only item that is
  not a page. We gave it to you because it is Shopify work.

### We supply

- The designs for each page.
- The quiz questions, their sequence, and each permitted answer.
- The API and its endpoints, as this document describes them.
- The email. We build the email and we send it. You do not touch it.
- The WhatsApp link and its prepared message.

### Not in this phase

- Customer accounts, a login, or a dashboard.
- A chat function.
- Plans that the customer keeps on more than one device.
- Work on the mobile app.

## Where the pages live

The pages are standalone pages on the Emerson Shopify store.

**We recommend a Shopify App Proxy at `/apps/concierge`.** The proxy keeps the pages on the
domain of the store. This gives you first-party cookies. It also prevents the failures that
occur when a browser blocks a cross-domain call.

The attribution from a plan to a purchase depends on the proxy. Include the proxy in your quote.
Tell us if you prefer a different method.

## The customer journey

```
   Quiz  ──submit──>  Status  ──────the email arrives──────>  (the customer leaves)
                         │
                    (optional)
                         │
                         v
                       Plan  ──>  Feedback
```

1. The customer answers the quiz.
2. The customer presses submit. We start work immediately. We tell the customer that the plan
   comes by email.
3. The status page gives the customer a choice. The customer can browse the store, or wait
   approximately 20 seconds and read the plan on the page.
4. The plan shows on the page if the customer waits.
5. The customer can then rate the plan.

The engine needs 10 to 20 seconds to make a plan. The customer can leave the page. This must not
stop the work or lose the plan.

## The endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /api/plan` | Sends the quiz answers. Returns a `plan_id` immediately |
| `GET /api/plan/{plan_id}` | The status poll, and the plan itself |
| `POST /api/plan/{plan_id}/feedback` | The rating |
| `POST /api/events` | The journey events |
| `GET /apps/concierge/go` | The product link. Records the click, then redirects |

---

## Page 1 — Quiz

The quiz asks a small number of questions about the hair of the customer. The last field is the
email address.

**We supply the questions, their sequence, and each permitted answer.** You do not write the hair
terminology. There are approximately ten questions. Most of them permit one answer.

Two fields need special controls:

- **One free-text field** — "What is going on with your hair right now?" This field is optional.
  Limit it to 1,000 characters. Our engine reads this field to find the problem, so the field is
  more important than its size shows.
- **Email** — required. We deliver the plan by email, so the customer must give an address.

The Consent and privacy section below gives the consent rules.

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

`texture`, `density` and `email` are required. Each other field is optional. `concern_text` can
be an empty string.

The response returns `202` immediately. It does not wait for the plan:

```json
{ "plan_id": "b6f1...", "status": "pending" }
```

Go to the status page with that `plan_id`.

### Requirements for this page

- **Do not write data to the device of the customer.** No `localStorage`, no `sessionStorage`,
  and no cookies. This rule is deliberate. It keeps the pages clear of storage consent and of
  private-window failures. The rule covers the answers, the `quiz_id`, and all other data.
- **The `submission_id` identifies one attempt, not one request.** Send the same value with each
  retry of the same quiz. We return the first plan for a repeated value, and we start no second
  run. Without this rule, a double press gives the customer two plans and two emails.
- **A failed submit must not lose the answers of the customer.**

---

## Page 2 — Status

The status page shows immediately after the submit action. This page lets the customer leave. Do
not keep the customer here.

Show two messages together:

- The plan is on its way to the inbox of the customer.
- The customer can browse the store, or wait approximately 20 seconds and read the plan here.

Give the customer a clear link back to the store. Most customers must use that link.

### `GET /api/plan/{plan_id}`

While the engine works:

```json
{ "plan_id": "b6f1...", "status": "pending" }
```

If the engine fails:

```json
{ "plan_id": "b6f1...", "status": "failed" }
```

The response carries `"status": "ready"` and the complete plan when the engine finishes. Page 3
gives that body.

An unknown `plan_id` returns `404`.

### Requirements for this page

- Do not poll more often than one time every 2 seconds.
- One failed poll is not an error. The poll must continue through a short network failure.
- Stop the poll at 45 seconds. Then tell the customer that the plan needs more time, and that
  the email will arrive. **This condition is normal. It is not an error.**
- The customer can leave the page safely. Do not show a message that asks the customer to stay.

---

## Page 3 — Plan

The plan page shows the routine. We supply the design. You build the page.

The page has a permanent public URL:

```
/apps/concierge/plan/{plan_id}
```

**The page must work with no other data.** There are two routes to this page. The second route is
the more frequent one:

1. From the status page, in the same sitting, seconds after the quiz.
2. From the email, some days later, in a different browser, with no quiz before it.

The page therefore reads all of its data from the `plan_id`. It must not need data from the quiz
page.

### The plan body

`GET /api/plan/{plan_id}` returns this body when `status` is `ready`:

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

- `you_told_us` — the words of the customer, shown back to them. It is null if the free-text
  field was empty.
- `summary` — a short paragraph about the hair of the customer.
- `concerns` — the problems that we found. The list can be empty.
- `climate_note` — one line about the local climate. It is null if the customer gave no location.
- `steps` — the routine in sequence.

The body does not change after `status` becomes `ready`. The plan is a permanent record, so the
customer sees the same plan on Friday as on Tuesday.

**Each field can be absent, except `summary` and `steps`.** This condition is normal. It is not
an error. The table below gives the action for each empty field. Build the page for incomplete
data from the start.

### Product availability

**We do not recommend a product that the store cannot sell.** The engine checks the catalog when
it makes the plan. The customer can buy each product on the page at that moment.

Show a buy button on each product. There is no availability call. There is no unavailable state
to design.

One condition remains, and it needs no work. A customer can open the email one week later and
find a product that the store sold out. The Shopify product page shows that condition.

### Product links

Each product has a `handle` for the URL and a `variant_id` for the cart. The catalog sync below
supplies both values.

Send each product click through this endpoint. It records the click, then it redirects:

```
GET /apps/concierge/go?plan_id=<plan_id>&shopify_id=<shopify_id>
    → 302 /products/<handle>?plan_id=<plan_id>
```

**Each link out of this page must carry the `plan_id`.** We store no data on the device of the
customer. The link is therefore the only connection between a quiz on Monday and a purchase on
Wednesday.

---

## Page 4 — Feedback

The plan page shows one question after the plan:

> How closely does this plan reflect what your hair currently needs?
> Very closely · Somewhat · Not quite · I'm not sure

The customer can also mark a product that they will not use, or a step that is not clear.

### `POST /api/plan/{plan_id}/feedback`

```json
{
  "rating": "very_closely",
  "rejected_shopify_ids": ["7412..."],
  "unclear_step": "clarify",
  "note": "free text, optional"
}
```

`rating` is one of `very_closely`, `somewhat`, `not_quite`, or `not_sure`. Each other field is
optional. The endpoint returns `202`. It accepts a repeated submission, and the last one wins.

The customer must not wait for this response. A lost rating costs us little. A delay costs us the
answer.

---

## The Shopify catalog sync

This is the only work here that is not a page.

Our recommendation engine knows the Emerson products from a product matrix spreadsheet. That data
uses the **SKU** as its key. It holds no Shopify identifiers: no product id, no variant id, no
handle, no current price, and no stock level. The engine can therefore name the correct product,
but it cannot make a link to it.

Each Shopify variant has a SKU field. The SKU is the join.

**The sync must give us this data** for each product in the matrix:

```
sku  →  product_id, variant_id, handle, title, price, available
```

That data gives us four things:

- the product URL, from the `handle`
- the add-to-cart call, from the `variant_id`
- the price on the product card
- the promise in this brief that we do not recommend a product that the store cannot sell

The data must stay current on a schedule. The handles and the prices change slowly. The stock
levels change more quickly. Tell us which schedule you recommend, and why.

**The location of the sync is open.** It can be a Shopify app on your side that sends the data to
us. It can also be a job on our side that calls the Shopify Admin API, with credentials that you
help us to scope. We gave the sync to you because the Shopify work is the difficult part. Tell us
which method you prefer. Give a separate price.

**Report each SKU that has no match.** A product in the matrix with no Shopify variant is a
product that we cannot sell. We need that list.

---

## Error states and empty states

Two rules control all of them:

1. **Incomplete data is normal.** Our engine returns an incomplete plan. It does not fail. The
   page must show the available data correctly.
2. **Few conditions are fatal, because we send the plan by email.** Each slow route and each
   failed route can end with the message "we will send the plan to your email".

### Empty fields on the plan page

| Field | Condition | Action |
| --- | --- | --- |
| `you_told_us` | The free-text field was empty | Hide the block. Do not show an empty quotation. |
| `concerns` | The engine found no problem | Hide the section. Do **not** write "no concerns found". That text tells the customer that the diagnosis failed. |
| `climate_note` | The customer gave no location | Hide the line. |
| `steps[].products` | No product matched the step | Show the step and its reason. Show no product cards. |
| The products in each step | No product matched at all | Show the routine. Add a link to a curator. |
| `summary` | The engine failed | Show the failure state for the complete plan. There is no content. |

### Failure states

| Condition | Action |
| --- | --- |
| The submit fails | Keep the answers. Give the customer a way to try again. |
| `status: failed` | Give a clear message. Offer WhatsApp. Offer a new quiz. Do not show a permanent progress indicator. |
| The status stays `pending` at 45 seconds | "This needs more time — we will send the plan to your email." This is not an error. |
| The `plan_id` is unknown | "This link is no longer available." Add a link to a new quiz. |
| The store sold out a product after the plan | No action. The Shopify product page shows the condition. |

Do not show error text, status codes, or stack traces to the customer. Each failure state must
give the customer a next action: a retry, WhatsApp, or the store.

---

## Tracking

We must know where customers stop the quiz, how long the quiz takes, and which recommendations
cause a purchase. `POST /api/plan` records only the completed quizzes. The events below give us
the data before the plan and after it.

### The two identifiers

There are no others.

| Identifier | Made by | Covers |
| --- | --- | --- |
| `quiz_id` | The client, at question one | The starts, the stops, and the time to completion |
| `plan_id` | The server, at plan creation | Each action after the plan |

The `quiz_id` must not go into `localStorage`, into `sessionStorage`, or into a cookie. The
customer completes the quiz in one sitting, so an identifier that ends with the browser tab is
sufficient. This keeps the pages clear of storage consent and of the Safari storage limits.

`POST /api/plan` carries the `quiz_id`, and we store it with the plan. That one field joins the
two halves of the journey.

### `POST /api/events`

Send the events in batches. Do not send one request for each event. The endpoint returns `202`.

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

- The envelope must contain the `quiz_id` or the `plan_id`. It contains both on the plan page
  when the customer arrives in the same sitting. It contains only the `plan_id` when the customer
  arrives from the email.
- Each event needs an `id` from the client. This `id` is the idempotency key. A repeated batch
  adds no new rows, so a poor connection cannot increase our counts.
- `occurred_at` is the browser clock, in ISO 8601 format, with a time zone.
- The limit for one batch is 50 events. The limit for `props` is 2 KB.
- The endpoint accepts `text/plain` and `application/json`. The last batch of a page can
  therefore use a transport that cannot set headers.

### The permitted events

This list is closed. **We refuse an unknown name.** A spelling error therefore fails with a
message. It does not make an event type that nobody counts.

| Name | Condition | props |
| --- | --- | --- |
| `quiz_started` | The first question shows | `referrer`, `utm`, `entry_path` |
| `quiz_step_viewed` | Each question shows | `step_index`, `question_id` |
| `quiz_step_answered` | The page accepts an answer | `step_index`, `question_id` |
| `quiz_submitted` | The customer presses submit | `step_count`, `free_text_used` |
| `plan_viewed` | The plan page shows | `revisit` (true or false) |
| `plan_step_expanded` | The customer opens a routine step | `step` |
| `product_clicked` | The customer presses a product link | `shopify_id`, `step` |
| `whatsapp_requested` | The customer presses the WhatsApp button | `step`, `origin` |
| `feedback_submitted` | The page sends the rating | `rating` |
| `plan_exited` | The page becomes hidden | `dwell_ms`, `deepest_step` |

Send `plan_viewed` with `revisit: true` when the customer arrives from the email.

### What you must not send

Three measures belong to the server. If the client sends them also, the two values disagree.
Somebody then quotes the weaker value.

- **The plan creation** — the plan record is the correct source. We calculate it.
- **The stopped quizzes** — do not send a `quiz_abandoned` event. A browser that closes cannot
  report correctly. We calculate this measure. A `quiz_id` with a start and no submit is a
  stopped quiz. Its highest `step_index` is the stop point. Send `quiz_step_viewed` correctly.
  That is sufficient.
- **The time to completion** — we calculate it from `quiz_started` to `quiz_submitted`.

### Requirements for the events

- **The last batch must arrive when the customer leaves the page.** This includes mobile Safari,
  where customers stop the quiz most frequently. The endpoint accepts `text/plain` for this
  reason.
- **A tracking failure must not stop a question, a submit, or a product link.**
- Do not send one request for each keystroke.

### The cart and the purchase

The quiz page and the plan page report their own events. Shopify holds the cart and the order.
Three Shopify functions cover those. You need no other analytics tool.

**The cart attributes and the line item properties.** The `plan_id` must reach the order in both
of these places when the customer adds a recommended product:

```
cart attribute        plan_id = <plan_id>
line item property    _plan_id = <plan_id>
```

The attribute goes to `order.note_attributes`. The property goes to the order line, and it
therefore gives us the attribution for each product. An empty cart loses the attribute, so the
cart needs the attribute again after each add.

**The web pixel extension.** Report `product_added_to_cart` and `checkout_completed`. The pixel
runs in a sandbox. It cannot read the variables in your page. The `plan_id` on the cart is
therefore the only connection between the plan page and the order. Keep the `plan_id` there.

**The `orders/paid` webhook is our work.** We read `note_attributes` and the line properties. We
then write the join. You do not build this.

### Tracking consent

Read `Shopify.customerPrivacy` before the first send. In some countries the page can send no
events. The measurement must lose data. It must not fail.

---

## Consent and privacy

- The email address is personal data. Give the customer a clear reason for it: we deliver the
  plan to that address.
- **The marketing consent is a separate checkbox. It starts empty.** The plan must not need a
  marketing consent.
- Put a link to the privacy policy on the quiz page, beside the email field.
- The Tracking section above gives the rules for the analytics consent.

We write no data to the device of the customer in this journey. This is deliberate. It keeps the
pages clear of storage consent.

---

## What we need in the quote

- A price for each page, so that we can remove one or delay one.
- A separate price for the App Proxy.
- A separate price for the tracking.
- A separate price for the catalog sync, with your recommendation for its location.
- Your assumptions about the items that we supply, and their dates.
- Your position on browser support, and on mobile Safari.

Plans do not expire. A plan link works permanently. You therefore build no expiry page.

Tell us what you need from us before you start, and when you need it: the designs, the questions,
the API access, and a store for development.
