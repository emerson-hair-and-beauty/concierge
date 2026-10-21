# Signal detection

Lives in `app/services/session_signal/`. Its job is to notice hair-health
problems the user mentions in passing during a chat, even if they never ask
about them directly, so the alerts pipeline (`ROADMAP.md`) can follow up.

## The six signals

Defined in `signal_detector.py`:

- `absorption_blocked` — hair repels moisture/product rather than absorbing it
- `hold_loss` — curls or styles lose shape and definition over time
- `breakage_active` — snapping, shedding, thinning, weak strands
- `buildup_present` — scalp or strands blocked by old product or sebum
- `coated_feel` — a waxy/filmy layer on the strand blocking moisture
- `scalp_sensitivity` — scalp irritation, itching, flaking, not from buildup

`scalp_sensitivity` is a later addition — older notes on this subsystem
describe only five signals. Check `signal_detector.py` itself, not past
write-ups, for the current list.

## Two-layer detection

`detect_signals()` runs a primary prompt (`_DETECTION_PROMPT`) with detailed
per-signal example phrases and explicit "do not flag for" exclusions (e.g.
`hold_loss` requires the curl's *shape* to degrade, not just frizz in one
spot). If every signal comes back false, it automatically runs a second,
different prompt (`_FALLBACK_PROMPT`), which reasons from the implied
situation rather than phrase-matching — meant to catch indirect descriptions
that don't hit any example phrase. The returned snapshot carries
`fallback_used: bool` so callers can tell which path produced the result.

On any exception, `detect_signals` returns all-false with
`fallback_used: False` rather than raising — detection failure degrades
silently rather than breaking the chat turn.

## Persistence

`session_signal_service.py`'s `process_session_signals()` is the entry
point (called from the web chat orchestrator's Pass 1.5 — see
[`chat-orchestration.md`](chat-orchestration.md)):

1. Runs `detect_signals()` on the last 10 messages of the conversation.
2. `signal_state.log_new_signals()` writes any newly-seen signal to the
   Supabase `signal_events` table — additive only, it never un-logs a
   signal once seen in this session.
3. `signal_state.get_session_snapshot()` reads back every signal ever
   logged for this `session_id` and merges in anything detected this turn,
   so a signal mentioned once early in a long conversation is still "on"
   many turns later.

If Supabase is unreachable, `log_new_signals` and `get_session_snapshot`
degrade to a no-op / all-false result via `app/services/resilience.py`'s
`safe_call` rather than raising. The practical effect of an outage: the
concierge loses memory of signals from *earlier* turns, but still acts on
whatever it detects in the *current* message, since the freshly-detected
result is OR'd onto the (possibly empty) snapshot.

This is a separate state store from the Observer's hair-trait profile
described in [`chat-orchestration.md`](chat-orchestration.md) — that one is
in-memory and per-process; this one is Supabase-backed and durable.

## Where this connects to customer data

[`enrichment-klaviyo.md`](enrichment-klaviyo.md) covers a pipeline that
appears to run this same kind of signal judging against Klaviyo guest
data, outside the live chat path — worth reading alongside this file if
you're trying to improve detection accuracy from real conversation data.
