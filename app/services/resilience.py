"""
Shared ledger for subsystems that are allowed to fail without taking a reply down
with them.

Originally this covered only Supabase-backed session state (signal history,
decision-state history): best-effort persistence for cross-turn memory, not the
source of truth for a single turn's response, so an outage should degrade to
stateless behaviour rather than crash the conversation. The tone guardrail
(app/services/tone_guard.py) has the same shape — losing it costs reply quality,
not the reply — so it reports here too, which is why `subsystem` and
`consequence` are parameters rather than baked into the message.

Every degradation is logged loudly and recorded so it's visible during testing
and demos instead of silently eating the outage — session memory loss is a real,
user-facing capability regression (decision states repeat instead of progressing,
signals mentioned in earlier turns are forgotten), not a cosmetic error.
"""
from datetime import datetime, timezone
from typing import Callable, Dict, List, TypeVar

T = TypeVar("T")

_degraded_events: List[Dict] = []


_SUPABASE_CONSEQUENCE = (
    "There is no fallback data store configured for this path — every\n"
    "  outage silently degrades every active conversation until Supabase\n"
    "  is reachable again."
)


def record_degraded_call(
    source: str,
    detail: str,
    error: Exception,
    subsystem: str = "Supabase",
    consequence: str = _SUPABASE_CONSEQUENCE,
) -> None:
    event = {
        "source": source,
        "detail": detail,
        "error": str(error),
        "subsystem": subsystem,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    _degraded_events.append(event)
    print(
        f"\n{'=' * 70}\n"
        f"[RESILIENCE GAP] {subsystem} unreachable in {source}\n"
        f"  Impact  : {detail}\n"
        f"  Error   : {error}\n"
        f"  {consequence}\n"
        f"{'=' * 70}\n"
    )


def get_degraded_events() -> List[Dict]:
    return list(_degraded_events)


def safe_call(fn: Callable[[], T], fallback: T, source: str, detail: str) -> T:
    try:
        return fn()
    except Exception as e:
        record_degraded_call(source, detail, e)
        return fallback
