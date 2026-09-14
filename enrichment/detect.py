"""Run signal detection over a whole conversation instead of one message.

Why this exists
---------------
`detect_signals` runs the fallback layer only when the first layer finds nothing:

    if _all_clear(signals):
        fallback = await _run_detection(_FALLBACK_PROMPT...)

Over one message that gate is right. Over a transcript of thirty messages at
least one signal fires almost every time, so `_all_clear` returns false and the
fallback layer never runs at all. Moving to one pass without changing the gate
would keep the layer that matches text and silently lose the layer that infers.

So this module runs both layers every time and merges the results. That costs one
extra call for a whole session, which is nothing when no customer waits for it.

On the private imports
----------------------
This reaches into `_DETECTION_PROMPT` and `_FALLBACK_PROMPT`. That is deliberate.
The chat pipeline is tested and works, and changing shared code to add a flag
risks it. Reaching in keeps the six signal definitions in one file, which matters
more. The cost is that a rename in `signal_detector` breaks this module.
`tests/test_enrichment.py` catches that.
"""

from __future__ import annotations

import asyncio
import contextlib
import io

from app.agents.llm_call.provider import generate_json
from app.services.session_signal.signal_detector import (
    _DETECTION_PROMPT,
    _FALLBACK_PROMPT,
    detect_signals,
)
from app.services.session_signal.signal_detector import SIGNAL_NAMES

# Appended after the transcript, so the stable prefix stays cacheable.
#
# `_run_detection` reads an `evidence_quote` off the response, but neither prompt
# ever asks for one, so it comes back empty nearly every time. That is why the
# report showed six bare labels and told you nothing.
#
# One quote for a whole call would not help much either. The question is which
# words fired WHICH signal, because `buildup_present` and `scalp_sensitivity`
# list the same example phrases and both fire on one complaint. So this asks for
# a quote per signal.
#
# "Quote the customer only" does a second job. If the model can only quote the
# assistant for a signal, that signal came from the agent's words, and you can
# see it happen instead of inferring it from totals.
_EVIDENCE_FORMAT = """

Return only JSON with this exact shape:
{"absorption_blocked": true or false, "hold_loss": true or false,
 "breakage_active": true or false, "buildup_present": true or false,
 "coated_feel": true or false, "scalp_sensitivity": true or false,
 "evidence": {"<each signal you marked true>": "<the customer's exact words>"},
 "confidence_score": 0.0 to 1.0}

Quote the CUSTOMER only. Never quote the assistant.
If you cannot quote the customer for a signal, that signal is false."""

# The chat pipeline sends the last ten messages. Kept the same so the per-message
# mode measures what production does, not a variation of it.
CHAT_WINDOW = 10

# Beyond this, recall falls for any single call, whichever layer runs.
MAX_TRANSCRIPT = 40

# Detection is read-only and cheap, but a burst still trips provider rate limits.
_MAX_PARALLEL = 4


def _conversation(messages: list[dict[str, str]]) -> str:
    """Build the transcript string. Mirrors `detect_signals` on purpose."""
    return "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content') or m.get('message', '')}"
        for m in messages
    )


@contextlib.contextmanager
def quiet():
    """Swallow the detector's own prints.

    `signal_detector` prints the transcript and the raw response on every call.
    That is useful when you debug one reply. Across twenty transcripts and three
    modes it buries the result, so the report writes the numbers instead.

    Wrap the whole run, never a single call. `redirect_stdout` swaps a global, so
    two of these open at once means the first one to exit restores stdout while
    the second still runs, and its output leaks into the report.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _empty() -> dict:
    return {k: False for k in SIGNAL_NAMES} | {"evidence": {}}


async def _run_with_evidence(prompt: str) -> dict:
    """Run one layer and keep the quote behind each signal."""
    result = await generate_json(prompt + _EVIDENCE_FORMAT)
    signals = {k: bool(result.get(k, False)) for k in SIGNAL_NAMES}
    raw = result.get("evidence")
    # Drop a quote for a signal the model marked false. It contradicts itself
    # often enough to matter, and a quote under a false signal reads as proof of
    # something that was never claimed.
    signals["evidence"] = {
        k: str(v).strip()
        for k, v in (raw or {}).items()
        if k in SIGNAL_NAMES and signals.get(k) and str(v).strip()
    }
    signals["confidence_score"] = result.get("confidence_score", 0.0)
    return signals


def _merge(*results: dict) -> dict:
    """OR the signals together. A signal found by any layer counts as found."""
    merged = _empty()
    for result in results:
        for name in SIGNAL_NAMES:
            merged[name] = merged[name] or bool(result.get(name))
    return merged


def active(signals: dict) -> set[str]:
    return {name for name in SIGNAL_NAMES if signals.get(name)}


async def detect_once(messages: list[dict[str, str]]) -> dict:
    """One pass over the transcript, with both layers forced.

    Returns the merged signals, plus `by_layer` so you can see which layer found
    what. The fallback layer infers rather than matches, and its findings deserve
    a higher confidence bar before they reach a customer profile.
    """
    window = messages[-MAX_TRANSCRIPT:]
    text = _conversation(window)

    primary, fallback = await asyncio.gather(
        _run_with_evidence(_DETECTION_PROMPT.format(conversation=text)),
        _run_with_evidence(_FALLBACK_PROMPT.format(conversation=text)),
        return_exceptions=True,
    )

    if isinstance(primary, Exception):
        print(f"[enrichment.detect] primary layer failed: {primary}")
        primary = _empty()
    if isinstance(fallback, Exception):
        print(f"[enrichment.detect] fallback layer failed: {fallback}")
        fallback = _empty()

    merged = _merge(primary, fallback)
    merged["by_layer"] = {"primary": sorted(active(primary)), "fallback": sorted(active(fallback))}
    # The matching layer quotes what the customer wrote. The fallback layer
    # reasons about it. Where both have a quote, the matching one is the better
    # evidence, so it wins.
    merged["evidence"] = {**fallback.get("evidence", {}), **primary.get("evidence", {})}
    merged["confidence_score"] = max(
        primary.get("confidence_score") or 0.0,
        fallback.get("confidence_score") or 0.0,
    )
    merged["truncated"] = len(messages) > MAX_TRANSCRIPT
    return merged


async def detect_per_message(messages: list[dict[str, str]]) -> dict:
    """Simulate the chat pipeline: detect at every customer turn, then accumulate.

    This is what `process_session_signals` does today, minus the database. Each
    customer turn gets the last ten messages, and `log_new_signals` only ever
    adds, so the result is the union across the conversation.
    """
    windows = [
        messages[max(0, i - CHAT_WINDOW + 1) : i + 1]
        for i, m in enumerate(messages)
        if m["role"] == "user"
    ]
    if not windows:
        return _empty() | {"calls": 0}

    gate = asyncio.Semaphore(_MAX_PARALLEL)

    async def one(window: list[dict[str, str]]) -> dict:
        async with gate:
            return await detect_signals(window)

    results = await asyncio.gather(*(one(w) for w in windows), return_exceptions=True)
    clean = [r for r in results if not isinstance(r, Exception)]
    for bad in (r for r in results if isinstance(r, Exception)):
        print(f"[enrichment.detect] per-message run failed: {bad}")

    merged = _merge(*clean)
    # Each run costs one call, plus a second when the first layer finds nothing.
    merged["calls"] = len(clean) + sum(1 for r in clean if r.get("fallback_used"))
    return merged
