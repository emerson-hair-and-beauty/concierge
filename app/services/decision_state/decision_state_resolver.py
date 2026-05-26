from typing import Dict


def resolve_decision_state(signals: Dict[str, bool]) -> str | None:
    if signals.get("breakage_active"):
        return "repair_first"
    if signals.get("buildup_present") or signals.get("absorption_blocked"):
        return "reset_first"
    return None
