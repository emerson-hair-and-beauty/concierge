# Review tooling

The human-in-the-loop system the brand expert uses to approve or reject
draft replies, and how those verdicts get traced back to the exact wording
that produced them. This is the "ongoing data collection" discussed with
your boss — it already exists; see the data-strategy doc you sent her.

## The investigative loop (`scripts/reviews.py`)

Four commands, run in sequence:

```
python scripts/reviews.py record              generate replies, save against
                                                the current prompt version
python scripts/reviews.py import verdicts.txt  paste back what the expert sent
python scripts/reviews.py stats                which settings get rejected
python scripts/reviews.py rejected             read every reply she turned down
```

The expert's side of this is deliberately frictionless: she clicks through
the review page, presses "Copy my answers," and sends the pasted text back.
No form, no format to learn — `import` parses that exact copied text.

## Why every reply is stamped with a prompt version

`app/services/prompt_version.py` hashes everything in
`response_composer.py` that can shape a reply — every always-on block and
every option in every table (each tone, each depth, each structure, each
decision-state note) — into a single version id. The hashing is done by
inspecting the actual prompt-building code, not a hardcoded list of what
"should" be included, specifically so a newly added block can't be silently
left out of the version and make a real change look like "nothing
changed."

This matters because review happens days after a reply is generated, and
the prompt keeps changing in between. Without the version id, "she rejected
this one" can't be traced to the wording responsible — it's just an
anecdote. With it, two version ids can be diffed to show exactly which
wording changed between a batch that scored well and one that didn't. This
is the mechanism behind the `ed7cedf1db2a` vs `847425ed0fc1` comparison in
`TONE_HANDOFF.md`.

## What a review record holds (`app/services/review_store.py`)

Stored in `data/reviews/<version>.json`. Each record: the reply, the
customer message that prompted it, the version id, and the exact options
selected (`decision_state`, `response_mode`, `response_depth`,
`tone_profile`, `cta_pressure`, `product_exposure` — these are
`review_store.DIMENSIONS`). `stats` reports approval rates broken down by
each dimension, always alongside the raw counts — the module's own
docstring warns that one rejection out of two reads as "50% approval" and
should be read as a pointer to what to investigate, never as a finding on
its own.

## Keeping it blind (`scripts/build_blind_review.py`)

Builds the actual review page (`blind_review.html` /
`repair_review.html` / `breakage_review.html` are examples of its output).
When comparing two prompt versions, the page deliberately shows no version
label, no batch heading, and shuffles replies with a fixed seed — so the
reviewer can't tell which replies are "the new ones" and mark them
accordingly. Every reply gets an opaque ticket (`r1`, `r2`, ...); her
copied answers map tickets back to records, and because every record kept
its real version internally, splitting her verdicts by version afterward is
automatic. Related: `scripts/blind_review_template.py`,
`scripts/build_review_artifact.py`.

## Where this feeds back in

`scripts/retrain_tone_from_feedback.py` is the path from these verdicts
into Simasia's `train_from_feedback()` — see
[`tone-guard-and-simasia.md`](tone-guard-and-simasia.md). That is also the
documented way out of the "trained on synthetic data, scored a coin flip"
problem: real approve/reject data, not generated paraphrases.
