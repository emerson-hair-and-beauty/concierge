import sys
import os
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.alerts.alert_service import process_alerts
from app.services.alerts.alert_state import get_sent_alert_types

USER_ID = f"test-alert-user-{uuid.uuid4().hex[:8]}"

EMPTY_SNAPSHOT = {
    "absorption_blocked": False,
    "hold_loss": False,
    "breakage_active": False,
    "buildup_present": False,
    "coated_feel": False,
}

SCENARIOS = {
    "1": {
        "label": "Dubai summer, no filtration, buildup signal",
        "snapshot": {**EMPTY_SNAPSHOT, "buildup_present": True},
        "env": {"temp_c": 38.0, "humidity": 75, "in_ac": False,
                "country": "UAE", "has_filtration": False},
    },
    "2": {
        "label": "Dubai winter indoors, AC on, breakage signal",
        "snapshot": {**EMPTY_SNAPSHOT, "breakage_active": True},
        "env": {"temp_c": 16.0, "humidity": 40, "in_ac": True,
                "country": "UAE", "has_filtration": False},
    },
    "3": {
        "label": "Mild climate, soft water, absorption + hold loss",
        "snapshot": {**EMPTY_SNAPSHOT, "absorption_blocked": True, "hold_loss": True},
        "env": {"temp_c": 22.0, "humidity": 55, "in_ac": False,
                "country": "UK", "has_filtration": True},
    },
    "4": {
        "label": "Empty snapshot, no env data (should produce 0 alerts)",
        "snapshot": EMPTY_SNAPSHOT,
        "env": {},
    },
    "5": {
        "label": "Repeat scenario 1 (dedup check — expect 0 new alerts)",
        "snapshot": {**EMPTY_SNAPSHOT, "buildup_present": True},
        "env": {"temp_c": 38.0, "humidity": 75, "in_ac": False,
                "country": "UAE", "has_filtration": False},
    },
}


def print_alerts(alerts):
    if not alerts:
        print("  (no new alerts)")
        return
    for a in alerts:
        print(f"  • [{a.source_type}/{a.source_id}] {a.alert_type}")
        print(f"      {a.message}")


def print_sent_log(user_id):
    sent = sorted(get_sent_alert_types(user_id))
    print(f"  sent so far ({len(sent)}): {', '.join(sent) if sent else '—'}")


def main():
    print("=" * 60)
    print("  Alerts Pipeline Test")
    print(f"  User ID: {USER_ID}")
    print("=" * 60)

    print("\nScenarios:")
    for key, sc in SCENARIOS.items():
        print(f"  [{key}] {sc['label']}")
    print("  [a] Run all in order")
    print("  [q] Quit")

    while True:
        choice = input("\nPick scenario: ").strip().lower()
        if choice in ("q", "quit", "exit"):
            break

        keys = list(SCENARIOS.keys()) if choice == "a" else [choice]
        for key in keys:
            sc = SCENARIOS.get(key)
            if not sc:
                print(f"  unknown choice: {key}")
                continue
            print(f"\n--- [{key}] {sc['label']} ---")
            new_alerts = process_alerts(USER_ID, sc["snapshot"], **sc["env"])
            print(f"  new alerts ({len(new_alerts)}):")
            print_alerts(new_alerts)
            print_sent_log(USER_ID)


if __name__ == "__main__":
    main()
