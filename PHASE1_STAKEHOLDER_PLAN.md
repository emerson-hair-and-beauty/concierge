# Curl Concierge Phase 1

For: Emerson. From: Engineering. Status: plan, 2026-09-03.

Implementation update, 2026-09-14: see [the implementation status](PHASE1_IMPLEMENTATION.md).
The supplier owns the catalog sync. Engineering receives and stores it through an API.
Step titles are fixed; one structured model response supplies personalized explanations.
Known fatal errors are recorded immediately. Generation and persistence have a 30-second total deadline.
Interrupted jobs are checked every five seconds and fail after 35 seconds, while the service runs.
The initial API route precedes integration and may use a direct Render URL.
These decisions supersede conflicting statements below. Customer launch has not occurred.

A readable version of `PHASE1_BACKEND_PLAN.md` and `PHASE1_DELIVERY_PLAN.md`. Same decisions,
same risks, without the schemas and the file paths. It adds nothing new.

Each item is marked with its owner: **[Emerson]**, **[Build]**, or **[Open]**.

---

## What exists today

The recommendation engine works. It is worth being precise about what that means, because it
sets the size of the remaining job.

A customer's answers go through four stages:

1. **Signal detection.** Free text is read for six problems — blocked absorption, loss of hold,
   active breakage, product build-up, a coated feel, and scalp sensitivity. The detector also
   returns the customer's own words as evidence for what it found.
2. **Decision state.** The profile and the signals resolve to one of eight states, such as
   *repair first*, *reset first* or *climate control first*. This is rules-based, not a model
   guess, so it is stable and testable.
3. **Routine constraints.** Each state produces an ordered list of steps, and a list of steps to
   avoid. *Repair first* mandates a gentle cleanse, then a protein treatment, then a moisture
   seal, and forbids heavy moisture until the repair is done.
4. **Product filters and search.** The state and the profile produce hard filters — required
   flags, forbidden flags, hold level, porosity — and a semantic search runs against the 256
   Emerson products.

The routine, the reasoning and the product shortlist all exist. What does not exist is any way to
deliver them. There is no endpoint that returns a structured plan, no stored plan, no email, and
no link between a recommended product and the Emerson shop.

---

## What we are adding

The shape of the new system, end to end:

```
Quiz on Shopify
   │  answers
   ▼
Our API  ──────────►  returns a plan reference in under a second
   │
   │  the work continues in the background, 10-20 seconds
   ▼
Engine  ──►  Plan record (frozen)  ──►  Email, via Klaviyo
                    │
                    ▼
            Plan page, on a permanent link
                    │
                    ▼
        Product click  ──►  Shopify cart  ──►  Order
                            (carrying the plan reference)
```

Five endpoints carry this: submit a quiz, read a plan, send feedback, record journey events, and
redirect a product click.

---

## The five decisions behind that shape

**The customer does not wait.** [Build] A plan takes 10 to 20 seconds. Rather than hold the
browser open, the submit returns immediately with a reference, and the plan is delivered by
email. A customer who wants to wait can, on a page that polls every two seconds. Most will not.

**The plan is frozen when it is made.** [Build] The plan is stored as a snapshot, not recomputed
on each visit. The rules will change as we improve them. A customer who opens their link on
Friday must see what they were told on Tuesday, or the plan is not a plan.

**One submission produces one plan.** [Build] The quiz sends a submission reference, and the
database enforces that it is unique. A double press, or a retry on a poor connection, returns the
first plan. It does not start a second run or send a second email.

**Nothing is stored on the customer's device.** [Build] No cookies and no browser storage. Two
references carry the journey instead: one held in the page for the length of the quiz, and the
plan reference, which we mint and which travels in the link, the cart and the order.

This keeps the pages clear of storage consent, and it avoids the failures that happen in private
browsing. There is one trade: a customer who returns weeks later without their link looks like a
new visitor to us. The plan link is what connects a quiz on Monday to a purchase on Wednesday,
which is why every link we send carries it.

**Product data is split in two.** [Build] The slow-moving knowledge — category, hold, porosity
rules — stays in the search index, which is expensive to rebuild. The fast-moving commercial data
— price, stock, the shop link — sits in a small table refreshed on a schedule. A search runs
against the first and joins to the second. Putting stock levels in the search index would mean
rebuilding it every time something sells out.

---

## Three gaps inside the engine

These are the parts that are genuinely missing, rather than undelivered.

**Products are not attached to routine steps.** [Build] The engine produces an ordered routine,
and separately produces a shortlist of suitable products. Nothing currently says which product is
the cleanse and which is the treatment. A plan page needs one product per step, so the search has
to run per step rather than once per plan.

**Products carry no Shopify identifiers.** [Build] Emerson's product matrix holds the expertise —
the categories, the hold levels, the rules about which product suits which hair. It holds no
shop link, no price and no stock level. So the engine can name the right product and cannot link
to it.

The fix is a pipeline that reads the live Shopify catalogue and joins it to the matrix, on a
schedule. It also reports every product in the matrix that Shopify cannot sell, which is useful
to Emerson on its own.

**Routine steps have no customer-facing names.** [Emerson] Internally a step is a code, such as
`gentle_cleanse`. The plan needs a name and one line explaining the purpose of each step. This is
brand copy, and it must read identically for every customer with the same routine, so it is
written once by hand rather than generated.

---

## Technical risks, named

| Risk | Owner | The problem | What we do |
|---|---|---|---|
| The server stalls under load | Build | The API runs a single process. Some database calls in the existing code are synchronous, which means one customer's plan generation can hold up everyone else's status checks. | Move those calls off the main path, then prove it with a load test: eight simultaneous submissions, and no status check slower than half a second. |
| A plan gets stuck | Build | The plan is generated inside the running process. A deploy or a restart kills it, and the record stays marked *in progress* for ever. The customer polls, sees nothing, and gets no email. | A sweeper marks any run older than ten minutes as failed, so the failure is visible instead of silent. |
| The catalogue empties quietly | Build | If the product refresh fails halfway, plans come out with no products. Plans are permanent snapshots, so those plans cannot be repaired afterwards. | Refuse any refresh that matches fewer than half the existing products, and raise an alert. |
| The generation time is wrong | Open | The 10 to 20 second figure has never been measured. The waiting page is designed around it — the copy, the two-second poll, and the point where it gives up and defers to email. | Time ten real runs before the front-end supplier finalises that page. This is the cheapest item on the plan and the one most likely to cause rework. |
| Two product sources disagree | Build | Two product data sets exist and both write to the same search index. It is not currently certain which one the live engine reads. If it is the wrong one, the join to Shopify fails from the start. | A one-hour check, before any catalogue work begins. |

---

## One gap in the range

The 256 products are not spread evenly across the steps of a routine.

| Routine category | Products |
|---|---|
| Styler | 70 |
| Conditioner | 53 |
| Moisturiser, leave-in | 43 |
| Shampoo, cleanser | 33 |
| Oils, refreshers | 23 |
| **Treatment** | **10** |

Treatment is the thin one. It is also the step the engine makes mandatory for any customer whose
hair is breaking, which is one of the most common reasons somebody takes a hair quiz.

The plan page handles this correctly: it shows the step and the reason, with no product card. But
a customer told that a protein treatment is their first priority, and then shown nothing to buy,
is a weak moment.

**This is a range decision, not an engineering one.** [Emerson] We will report how often it
happens from the first week.

---

## Measurement

Thirteen things are tracked, using Shopify's own features and our own records. No third-party
analytics product is needed, and nothing is stored on the customer's device.

Three mechanisms cover all of it:

- **Our own event record.** Everything on our pages: starts, each question viewed and answered,
  submissions, plan views, product clicks, WhatsApp requests and ratings.
- **The plan reference on the cart.** When a customer adds a recommended product, the plan
  reference is written onto the cart and onto the line item. It reaches the order, which gives
  attribution for each individual product, not just the sale.
- **The order webhook.** Shopify tells us when an order is paid. We read the reference and write
  the join.

Four measures are calculated by us rather than reported by the browser: plan creation, abandoned
quizzes, time to completion, and purchases. A browser that closes cannot report reliably, and two
sources that disagree mean somebody eventually quotes the weaker number.

**What this answers.** How many people find the quiz and where from; how many start and finish;
which question loses them; what was recommended and why; what was clicked, added and bought;
which purchases came from a plan; who asked for a curator; and who said the plan was wrong.

That last pair matters most. A plan that generates successfully and a plan the customer finds
useful are two different things. Only the second tells Emerson whether the engine is good.

**Phase 2 should not be scoped until this data exists.** It answers whether there is real demand,
whether the completion rate holds, whether the recommendations are accurate enough, and whether
people return. Those answers should shape what is built next, rather than a feature list agreed
in advance.

---

## How we will know Phase 1 is finished

A customer can find the diagnostic, complete it, receive a plan by email, read it on a permanent
link, buy the products, ask a curator for help, and rate the result — without anyone at Emerson
touching it.

And Emerson can answer, from the data and without asking engineering: how many people started,
where the rest stopped, how long it took, what was recommended, what sold, and which plans
customers said were wrong.

The engine is the part that already works. The remaining risk sits in the delivery layer, the
range, the traffic, and the questions we ask.
