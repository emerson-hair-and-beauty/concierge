# Clarification

`app/services/clarification/clarification_generator.py` — one LLM call.
When signal detection can't confidently place a customer's message, this
writes one short clarifying question plus 3-4 plain-language answer
options (always ending in "Not sure — it just feels off"), each mapped to
one of the six signals from [`signal-detection.md`](signal-detection.md).
The prompt is explicit that options must read like "a knowledgeable friend
speaking, not a medical form," and must quote the customer's own wording
back to them.

On any failure, it falls back to a fixed, hand-written version of the same
question covering four of the six signals, rather than raising.

Its only caller is `app/services/decision_state/pipeline.py`'s
`ClarificationRequest` flow — the engine behind the dashboard's chat (mode
4 in `README.md`; see
[`decision-state-and-tone.md`](decision-state-and-tone.md)). It is working
code with a real UI: the dashboard renders the question as a radio-button
list. It just isn't reachable from a customer-facing route today.
