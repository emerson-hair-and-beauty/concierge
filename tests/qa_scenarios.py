"""
QA scenario test — runs all 30 feedback scenarios through the full pipeline.
Tests decision state routing, JTE mode/depth, and signal detection.

Run from project root:
    python tests/qa_scenarios.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.decision_state.models import (
    ProfileState, EnvironmentalContext, SessionSignal,
    ResponseComposerInput,
)
from app.services.session_signal.signal_detector import detect_signals, SIGNAL_NAMES
from app.services.decision_state.decision_engine import build_strategy_payload
from app.services.decision_state.jte import resolve_delivery_plan
from app.services.session_intent.session_intent_service import process_session_intent
from app.services.decision_state.response_composer import compose_response

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

P4B = ProfileState(
    texture_type="4B", texture_label="Dense Coils",
    porosity="high", density="high", elasticity="low",
    humidity_response="high sensitivity",
    routine_flags=["seal_moisture", "frizz_control"],
)
P3C = ProfileState(
    texture_type="3C", texture_label="Tight Curls",
    porosity="low", density="medium", elasticity="normal",
    humidity_response="moderate sensitivity",
    routine_flags=["frizz_control"],
)
P4A = ProfileState(
    texture_type="4A", texture_label="Loose Coils",
    porosity="medium", density="high", elasticity="normal",
    humidity_response="low sensitivity",
    routine_flags=["seal_moisture"],
)

# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

ENV_GCC = EnvironmentalContext(humidity_level="high", heat_stress="high", hard_water=False, ac_exposure="high")
ENV_HW  = EnvironmentalContext(humidity_level="medium", heat_stress="low", hard_water=True)
ENV_LOW = EnvironmentalContext(humidity_level="low", heat_stress="low", hard_water=False)

# ---------------------------------------------------------------------------
# 30 QA scenarios  (label, user_message, profile, env, expected_decision_state)
# ---------------------------------------------------------------------------

SCENARIOS = [
    ("01 Dubai humidity frizz",
     "My hair is so frizzy in this Dubai humidity, my curls collapse within hours",
     P4B, ENV_GCC, "climate_control_first"),

    ("02 UAE summer curl definition collapse",
     "Living in the UAE, the summer heat and humidity destroys my curl definition every day",
     P4B, ENV_GCC, "climate_control_first"),

    ("03 Itchy flaky scalp",
     "My scalp has been really itchy and flaky lately, it feels sore after styling",
     P4A, ENV_GCC, "scalp_calm_first"),

    ("04 Hair snapping breakage",
     "My hair keeps snapping when I detangle, I see lots of short broken pieces everywhere",
     P4B, ENV_GCC, "repair_first"),

    ("05 Curls lose definition fast (low humidity)",
     "My curls lose definition and shape within hours of styling",
     P3C, ENV_LOW, "hold_and_definition_first"),

    ("06 Overwhelmed by products",
     "I have tried so many products and routines, nothing works, I am completely overwhelmed and defeated",
     P4A, ENV_GCC, "simplify_and_reduce_friction"),

    ("07 New to curly hair routine",
     "I am new to taking care of my curly hair, I have no idea where to even start",
     P3C, ENV_GCC, "balanced_routine_first"),

    ("08 UAE summer frizz immediately",
     "UAE summer is absolutely destroying my curls, they frizz up the moment I step outside",
     P4B, ENV_GCC, "climate_control_first"),

    ("09 Routine working great reinforce",
     "My routine has been working really well lately, my curls look amazing and healthy",
     P3C, ENV_LOW, "reinforce_current_routine"),

    ("10 Child with sensitive scalp",
     "My child has a very sensitive scalp that is always itchy and gets irritated easily",
     P4A, ENV_GCC, "scalp_calm_first"),

    ("11 Styles not lasting hold loss (low humidity)",
     "My gel never defines my curls for long, they lose shape and go frizzy by noon",
     P3C, ENV_LOW, "hold_and_definition_first"),

    ("12 Shedding weak brittle hair",
     "I have been seeing a lot of shedding lately, my hair feels weak and brittle",
     P4B, ENV_GCC, "repair_first"),

    ("13 Products sitting on top absorption",
     "Products just sit on top of my hair and refuse to absorb, no matter what I try",
     P4B, ENV_GCC, "reset_first"),

    ("14 Waxy coated hair",
     "My hair feels waxy and coated even right after I wash it, like there is a film on it",
     P3C, ENV_LOW, "reset_first"),

    ("15 Scalp heavy products stopped working",
     "My scalp feels heavy and my products seem to have completely stopped working",
     P4A, ENV_GCC, "reset_first"),

    ("16 High porosity high humidity",
     "I have high porosity 4C curls in Dubai humidity, I get constant frizz no matter what I use",
     P4B, ENV_GCC, "climate_control_first"),

    ("17 Post-purchase how to use",
     "I just bought the leave-in conditioner you recommended, how do I layer it with my styler?",
     P3C, ENV_GCC, "balanced_routine_first"),

    ("18 No definition after day 1 (low humidity)",
     "After day one my curls look completely messy and undefined, hold never lasts",
     P3C, ENV_LOW, "hold_and_definition_first"),

    ("19 Hard water dull dry hair",
     "We have very hard water and my hair is dull, dry and nothing absorbs properly anymore",
     P4A, ENV_HW, "reset_first"),

    ("20 AC drying hair silently",
     "The AC in Dubai is making my hair incredibly dry from the inside, it feels dehydrated all the time",
     P4B, ENV_GCC, "climate_control_first"),

    ("21 Too many routine steps friction",
     "My routine has too many steps, it takes hours and I never know what I can safely skip",
     P4A, ENV_GCC, "simplify_and_reduce_friction"),

    ("22 Crunch-free curls in heat",
     "I want crunch-free defined curls that actually last through the heat and humidity here",
     P3C, ENV_GCC, "climate_control_first"),

    ("23 Scalp irritated after styling",
     "After I style my hair my scalp gets red and very irritated, I think a product is causing it",
     P4A, ENV_GCC, "scalp_calm_first"),

    ("24 Hair not growing breaking",
     "My hair never seems to grow past a certain length, it just keeps breaking off at the ends",
     P4B, ENV_GCC, "repair_first"),

    ("25 Want simple routine",
     "I want the simplest possible curl routine, I cannot deal with complicated any more",
     P4A, ENV_GCC, "simplify_and_reduce_friction"),

    ("26 Scalp itching after braiding",
     "My scalp has been really itchy since I had my hair braided last week, it is sore too",
     P4B, ENV_GCC, "scalp_calm_first"),

    ("27 4C moisture retention general",
     "I have 4C hair and really struggle to keep moisture in between wash days",
     P4B, ENV_GCC, "balanced_routine_first"),

    ("28 High porosity UAE summer constant frizz",
     "I have high porosity hair in UAE summer, frizz is constant and humidity ruins everything",
     P4B, ENV_GCC, "climate_control_first"),

    ("29 Ends dry splitting breakage",
     "My ends are constantly dry and splitting, the breakage is getting worse and worse",
     P4B, ENV_GCC, "repair_first"),

    ("30 Not sure if need protein",
     "I think my hair might need protein but I am honestly not sure, things just feel off lately",
     P3C, ENV_LOW, "balanced_routine_first"),
]


async def run_routing_check(label, message, profile, env, expected):
    messages = [{"role": "user", "content": message}]
    sigs, intent = await asyncio.gather(
        detect_signals(messages),
        process_session_intent(messages),
    )
    ss = SessionSignal(**{k: sigs.get(k, False) for k in SessionSignal.model_fields if k in sigs})
    strategy = build_strategy_payload(profile, ss, env, intent)
    delivery = resolve_delivery_plan(strategy.jte_input, strategy.decision_state)
    active = [k for k in SIGNAL_NAMES if sigs.get(k)]
    return {
        "label":    label,
        "expected": expected,
        "got":      strategy.decision_state,
        "signals":  active,
        "mode":     delivery.response_mode,
        "depth":    delivery.response_depth,
        "tone":     delivery.tone_profile,
        "pass":     strategy.decision_state == expected,
    }


async def run_full_response(label, message, profile, env):
    messages = [{"role": "user", "content": message}]
    sigs, intent = await asyncio.gather(
        detect_signals(messages),
        process_session_intent(messages),
    )
    ss = SessionSignal(**{k: sigs.get(k, False) for k in SessionSignal.model_fields if k in sigs})
    strategy = build_strategy_payload(profile, ss, env, intent)
    delivery = resolve_delivery_plan(strategy.jte_input, strategy.decision_state)
    ci = ResponseComposerInput(
        strategy_payload=strategy, jte_delivery_plan=delivery,
        profile_state=profile, env=env,
        candidate_products=[], recent_messages=messages,
    )
    text = ""
    async for chunk in compose_response(ci):
        if chunk.get("type") == "content":
            text += chunk["content"]
    return text


async def main():
    print("=" * 70)
    print("  EMERSON QA SCENARIO TEST - 30 SCENARIOS")
    print("=" * 70)

    # Phase 1: routing check for all 30
    print("\nPHASE 1 - Decision state routing\n")
    results = []
    for s in SCENARIOS:
        r = await run_routing_check(*s)
        results.append(r)
        tag = "PASS" if r["pass"] else "FAIL"
        print(f"  [{tag}] {r['label']}")
        if not r["pass"]:
            print(f"         expected={r['expected']}")
            print(f"         got     ={r['got']}")
        print(f"         signals={r['signals'] or ['none']}  {r['mode']}/{r['depth']}  {r['tone']}")

    passed = sum(1 for r in results if r["pass"])
    print(f"\n  Routing: {passed}/{len(results)} passed\n")

    # Phase 2: full response for one scenario per new state
    print("=" * 70)
    print("PHASE 2 - Response quality (one per new decision state)")
    print("=" * 70)

    sample = [
        ("scalp_calm_first",             SCENARIOS[2]),
        ("climate_control_first",         SCENARIOS[0]),
        ("repair_first",                  SCENARIOS[3]),
        ("hold_and_definition_first",     SCENARIOS[4]),
        ("reinforce_current_routine",     SCENARIOS[8]),
        ("simplify_and_reduce_friction",  SCENARIOS[5]),
    ]

    for state, (label, message, profile, env, expected) in sample:
        print(f"\n--- {label} ({state}) ---")
        print(f"User: \"{message}\"")
        response = await run_full_response(label, message, profile, env)
        print(f"\nResponse ({len(response)} chars):")
        print(response)

if __name__ == "__main__":
    asyncio.run(main())
