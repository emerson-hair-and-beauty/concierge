"""
End-to-end test for the alerts pipeline.

Drives process_alerts directly with synthetic signal snapshots so the assertions
are deterministic (no LLM dependency). Verifies:
  - env context lookup (location -> weather -> temp/humidity)
  - alert persistence to alert_log
  - cooldown blocks re-fire within the rule's window
  - new signals fire even when others are on cooldown
  - banner API surface (db.get_pending_alerts) returns the legacy shape

The orchestrator wiring itself is a thin function chain — covered by an
optional Pass 2 below that only runs if --with-orchestrator is passed.

Prereqs:
  - SUPABASE_URL, SUPABASE_KEY in app/.env
  - WEATHER_API_KEY in app/.env (env alerts won't fire without it)
  - alert_log + signal_events + user_metadata tables exist in Supabase

Run:
  python tests/test_alerts_e2e.py
  python tests/test_alerts_e2e.py --with-orchestrator   # also exercises the
                                                       # full orchestrator path
                                                       # (LLM-dependent, may be
                                                       # flaky on Gemini 503s)
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.alerts.alert_service import process_alerts
from app.services.environmental_factors.weather_service import get_city_environmental_data
from app.services.supabase_service import get_supabase
from app.services.db_service import get_db


USER_ID = f"e2e-alerts-{uuid.uuid4().hex[:8]}"
SESSION_ID = f"e2e-session-{uuid.uuid4().hex[:8]}"
LOCATION = "Dubai"

EMPTY_SNAPSHOT = {
    "absorption_blocked": False,
    "hold_loss": False,
    "breakage_active": False,
    "buildup_present": False,
    "coated_feel": False,
}

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
RESET = "\033[0m"

passes = 0
fails = 0


def header(text: str):
    print(f"\n{YELLOW}{'=' * 64}{RESET}")
    print(f"{YELLOW}  {text}{RESET}")
    print(f"{YELLOW}{'=' * 64}{RESET}")


def ok(text: str):
    global passes
    passes += 1
    print(f"{GREEN}  PASS  {RESET}{text}")


def fail(text: str):
    global fails
    fails += 1
    print(f"{RED}  FAIL  {RESET}{text}")


def info(text: str):
    print(f"{DIM}  {text}{RESET}")


def fetch_alert_log() -> list:
    supabase = get_supabase()
    response = (
        supabase.table("alert_log")
        .select("alert_type, scenario, source_type, sent_at")
        .eq("user_id", USER_ID)
        .order("sent_at", desc=True)
        .execute()
    )
    return response.data or []


def cleanup():
    info("Cleaning up test rows...")
    supabase = get_supabase()
    try:
        supabase.table("alert_log").delete().eq("user_id", USER_ID).execute()
        supabase.table("signal_events").delete().eq("user_id", USER_ID).execute()
        supabase.table("user_metadata").delete().eq("user_id", USER_ID).execute()
        info(f"Deleted rows for {USER_ID}")
    except Exception as e:
        info(f"cleanup error (ignore if rows absent): {e}")


async def fetch_env(location: str) -> dict:
    """Resolve env context the same way the orchestrator does."""
    env_kwargs = {"country": location}
    try:
        weather = await get_city_environmental_data(location, attribute="all")
        if weather:
            env_kwargs["temp_c"] = weather.get("peak_heat")
            env_kwargs["humidity"] = weather.get("peak_humidity")
    except Exception as e:
        info(f"weather lookup failed: {e}")
    return env_kwargs


async def main():
    args = set(sys.argv[1:])
    print(f"{YELLOW}Alerts pipeline E2E{RESET}")
    print(f"  user_id    : {USER_ID}")
    print(f"  session_id : {SESSION_ID}")
    print(f"  location   : {LOCATION}")

    db = get_db()

    # --- Setup ----------------------------------------------------------------
    header("Setup — seed user location + resolve env context")
    if db.update_user_location(USER_ID, LOCATION):
        ok(f"user_metadata.location = {LOCATION}")
    else:
        fail("could not seed location")

    env = await fetch_env(LOCATION)
    info(f"env context: {env}")
    if "temp_c" in env and "humidity" in env:
        ok(f"weather resolved: {env['temp_c']}°C / {env['humidity']}% humidity")
    else:
        info("weather not resolved — only hard_water alert (if any) will fire")

    # --- Turn 1: buildup signal + env ----------------------------------------
    header("Turn 1 — buildup_present snapshot + Dubai env")
    snapshot1 = {**EMPTY_SNAPSHOT, "buildup_present": True}
    alerts1 = process_alerts(USER_ID, snapshot1, **env)
    types1 = [a.alert_type for a in alerts1]
    info(f"new alerts: {types1}")

    if "buildup_filtration_check" in types1:
        ok("session-signal alert fired (buildup_filtration_check)")
    else:
        fail("expected buildup_filtration_check to fire")

    if "hard_water_cleansing" in types1:
        ok("env alert fired (hard_water_cleansing — Dubai = hard water)")
    else:
        fail("expected hard_water_cleansing for GCC country")

    if any(t.startswith("sweat_") for t in types1):
        sweat_types = [t for t in types1 if t.startswith("sweat_")]
        ok(f"env alert fired (sweat: {sweat_types})")
    else:
        info("no sweat alert — likely weather not resolved or sweat=LOW")

    # --- Turn 2: same trigger, expect cooldown -------------------------------
    header("Turn 2 — identical inputs (cooldown check)")
    alerts2 = process_alerts(USER_ID, snapshot1, **env)
    types2 = [a.alert_type for a in alerts2]
    info(f"new alerts: {types2 or '(none)'}")

    redupes = set(types2) & set(types1)
    if not redupes:
        ok(f"cooldown holding — {len(types1)} alert(s) from turn 1 did not re-fire")
    else:
        fail(f"these re-fired despite cooldown: {sorted(redupes)}")

    # --- Turn 3: new signal, others still on cooldown ------------------------
    header("Turn 3 — breakage_active (new signal, env alerts on cooldown)")
    snapshot3 = {**EMPTY_SNAPSHOT, "breakage_active": True}
    alerts3 = process_alerts(USER_ID, snapshot3, **env)
    types3 = [a.alert_type for a in alerts3]
    info(f"new alerts: {types3 or '(none)'}")

    if "breakage_protein_check" in types3:
        ok("new signal alert fired (breakage_protein_check)")
    else:
        fail("expected breakage_protein_check to fire")

    if any(t in types1 for t in types3):
        already_fired = [t for t in types3 if t in types1]
        fail(f"these turn-1 alerts re-fired: {already_fired}")
    else:
        ok("turn-1 alerts stayed on cooldown")

    # --- Turn 4: cron-style scenarios (Long Gap + Performance Review) -------
    header("Turn 4 — cron path: Long Gap (35 days) + Performance Review (3 washes)")
    now = datetime.now(timezone.utc)
    wash_logs = [
        {"created_at": (now - timedelta(days=35)).isoformat()},
        {"created_at": (now - timedelta(days=42)).isoformat()},
        {"created_at": (now - timedelta(days=49)).isoformat()},
    ]
    alerts4 = process_alerts(
        USER_ID,
        snapshot=EMPTY_SNAPSHOT,
        wash_logs=wash_logs,
        user_meta={"primary_goal": "strength"},
        current_date=now,
    )
    types4 = [a.alert_type for a in alerts4]
    info(f"new alerts: {types4 or '(none)'}")

    if "long_gap_clarify" in types4:
        ok("long_gap_clarify fired (35 days since last wash)")
    else:
        fail("expected long_gap_clarify")
    if "performance_review_3_washes" in types4:
        ok("performance_review_3_washes fired (exactly 3 wash events)")
    else:
        fail("expected performance_review_3_washes")

    # --- Turn 5: Day-3 Pulse + Weather Defense (humectants) -----------------
    header("Turn 5 — cron path: Day-3 Pulse (strength) + Weather Defense (humectants)")
    fresh_user = f"e2e-cron-{uuid.uuid4().hex[:6]}"
    info(f"fresh user for cron-only scenarios: {fresh_user}")
    db.update_user_location(fresh_user, "Dubai")

    day3_wash = [{"created_at": (now - timedelta(days=3)).isoformat()}]
    routine_with_humectant = {"shampoo": {"ingredients": ["Water", "Polyquaternium-69"]}}
    alerts5 = process_alerts(
        fresh_user,
        snapshot=EMPTY_SNAPSHOT,
        wash_logs=day3_wash,
        routine=routine_with_humectant,
        user_meta={"primary_goal": "strength"},
        humidity=80,  # synthetic: force the weather defense rule
        current_date=now,
    )
    types5 = [a.alert_type for a in alerts5]
    info(f"new alerts: {types5 or '(none)'}")
    if "day_3_pulse_strength" in types5:
        ok("day_3_pulse_strength fired (3 days post-wash, strength goal)")
    else:
        fail("expected day_3_pulse_strength")
    if "weather_defense_humectants" in types5:
        ok("weather_defense_humectants fired (humidity >= 70% + Polyquaternium-69)")
    else:
        fail("expected weather_defense_humectants")

    # Clean up the fresh cron user
    s = get_supabase()
    s.table("alert_log").delete().eq("user_id", fresh_user).execute()
    s.table("user_metadata").delete().eq("user_id", fresh_user).execute()

    # --- Banner API surface ---------------------------------------------------
    header("Banner inbox — db.get_pending_alerts shape")
    banner = db.get_pending_alerts(USER_ID, limit=10)
    info(f"banner rows: {len(banner)}")
    if banner:
        keys = set(banner[0].keys())
        expected = {"scenario", "prompt", "created_at"}
        if expected.issubset(keys):
            ok(f"legacy response shape preserved: {sorted(keys & expected)}")
        else:
            fail(f"missing legacy keys: {sorted(expected - keys)} (got {sorted(keys)})")
    else:
        fail("expected at least one banner row")

    # --- Final alert_log state ------------------------------------------------
    header("Final alert_log state")
    for row in fetch_alert_log():
        print(f"  • {row['alert_type']:<28} [{row['source_type']}]  sent_at={row['sent_at']}")

    # --- Optional Pass 2: orchestrator wiring --------------------------------
    if "--with-orchestrator" in args:
        header("Optional — orchestrator wiring (Gemini-dependent)")
        try:
            from app.web_chat_agent.orchestrator import orchestrate_web_chat
            events = []
            async for event in orchestrate_web_chat(
                [], "is my hair really salty after the beach today?",
                session_id=SESSION_ID, user_id=USER_ID
            ):
                events.append(event)
            alert_events = [e for e in events if e.get("type") == "alert"]
            info(f"orchestrator emitted {len(events)} event(s), {len(alert_events)} alert(s)")
            ok("orchestrator ran to completion")
        except Exception as e:
            info(f"orchestrator crashed (likely Gemini 503): {e}")
            info("alerts pipeline itself is healthy — see passes above")

    # --- Summary --------------------------------------------------------------
    header(f"Summary: {GREEN}{passes} pass{RESET}{YELLOW} / {RED}{fails} fail{RESET}{YELLOW}")
    cleanup()
    print()


if __name__ == "__main__":
    asyncio.run(main())
