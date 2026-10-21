# Enrichment: WhatsApp → signals → Klaviyo

Lives in `enrichment/`. This is an offline research pipeline, run by hand
via `python -m enrichment.<module>`, not a live service. **It is about
WhatsApp support conversations, not the Klaviyo guest-export CSVs
discussed earlier in this project's data-strategy conversation** — related
idea, different input. Don't conflate the two.

## Why it exists

The business WhatsApp number runs in the WhatsApp Business app, not on the
Cloud API, and no webhook delivers those conversations today (that needs a
Coexistence Solution Partner). The only data available is the export the
app itself writes: open a chat → "Export chat" → "Without media."

## The pipeline

1. **`parse_export.py`** — parses that export (Android and iOS use
   different formats) into pipeline turns.
2. **`contacts.py`** — finds the email and name in the conversation.
   Email uses a regex, deliberately not a model: a model can invent an
   address, and a wrong address in a marketing profile reaches a real
   person. The name is handled by a model, since "I'm Sarah" and "my sister
   Sarah has the same problem" are only distinguishable by judgment.
3. **Signal detection, run three different ways, to answer two open
   questions** (`compare.py`):
   - **`detect.py`** — runs the live detector's two layers
     (`_DETECTION_PROMPT` and `_FALLBACK_PROMPT`, imported directly from
     `app/services/session_signal/signal_detector.py`) over the *whole*
     transcript and merges them. This exists because the live gate only
     runs the fallback layer when the first layer finds nothing — true for
     one message, almost never true over a 30-message transcript, so a
     naive one-pass version would silently lose the inference layer.
   - **`signal_judge.py`** — a from-scratch prompt, with no example
     phrases, that is strict about attribution: it only counts something
     as a signal if the *customer* said it, not the assistant repeating the
     problem back. On WhatsApp the assistant is a human agent, and people
     restate problems ("so the breakage started after you changed
     shampoo?") in a way the live detector was never tuned to ignore.
   - **`compare.py`** prints the difference between all three, specifically
     to measure "both sides found it, customer-only judge did not" — i.e.
     whether the live detector is picking up false signals from the
     agent's own words on WhatsApp.
4. **`klaviyo.py`** — sends the detected signals to Klaviyo **as an event,
   not a profile property**, specifically so a new signal doesn't overwrite
   the history of an older one (a property would lose the fact that the
   same customer reported breakage a month ago; an event lets Klaviyo
   segment on "has WhatsApp Signal Detected = breakage_active, ever").
   Three API calls in sequence: `profile-import` → add to list →
   `events`. **Nothing sends by default** — the payload prints and only
   leaves the machine with `--send`, and the module refuses to send if
   there's no email or phone to match an existing profile, because a wrong
   match silently creates an unmergeable duplicate profile with no undo.
5. **`calibrate_judge.py`** — audits `signal_judge.py` against real,
   previously-misjudged examples (several are Kety's actual words, pulled
   from `_chat.txt`) before trusting it to write to anyone's profile. Same
   discipline `scripts/calibrate_judge.py` applies to the tone judge, and
   for the same stated reason: an unaudited judge always looks fine until
   someone checks.

## Why this matters for the ongoing-data-collection conversation

This pipeline already solves, for WhatsApp, the exact problem raised with
your boss: pairing real customer language with a judged outcome, and
feeding it somewhere durable (Klaviyo) rather than letting it evaporate
after one conversation. It does not yet touch the Typeform/Recovery-State
data from that conversation — extending it to cover that source, or
building an equivalent for it, is open work, not something this pipeline
already does.
