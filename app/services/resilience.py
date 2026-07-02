"""
Shared guard for Supabase-backed session state (signal history, decision-state
history). These stores are best-effort persistence for cross-turn memory, not
the source of truth for a single turn's response — if Supabase is unreachable,
degrade to stateless behaviour rather than crashing the conversation.

Every degradation is logged loudly and recorded so it's visible during testing
and demos instead of silently eating the outage — session memory loss is a real,
user-facing capability regression (decision states repeat instead of progressing,
signals mentioned in earlier turns are forgotten), not a cosmetic error.
"""
from datetime import datetime, timezone
from typing import Callable, Dict, List, TypeVar

T = TypeVar("T")

_degraded_events: List[Dict] = []


def record_degraded_call(source: str, detail: str, error: Exception) -> None:
    event = {
        "source": source,
        "detail": detail,
        "error": str(error),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    _degraded_events.append(event)
    print(
        f"\n{'=' * 70}\n"
        f"[RESILIENCE GAP] Supabase unreachable in {source}\n"
        f"  Impact  : {detail}\n"
        f"  Error   : {error}\n"
        f"  There is no fallback data store configured for this path — every\n"
        f"  outage silently degrades every active conversation until Supabase\n"
        f"  is reachable again.\n"
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
