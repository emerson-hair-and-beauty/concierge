"""
Emerson Concierge — Live Pipeline Demo
Shows every decision the AI makes before composing a response.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.decision_state.models import ProfileState, EnvironmentalContext
from app.services.session_signal.signal_detector import detect_signals
from app.services.session_intent.intent_detector import detect_intent
from app.services.decision_state.decision_engine import build_strategy_payload
from app.services.decision_state.jte import resolve_delivery_plan
from app.services.decision_state.models import SessionSignal
from app.services.decision_state.response_composer import compose_response
from app.services.decision_state.models import ResponseComposerInput
from app.agents.recommendation.lib.knowledge_base.query_products import query_products

# ---------------------------------------------------------------------------
# Demo scenario — change this to show different paths
# ---------------------------------------------------------------------------

SCENARIO = {
    "name": "Frustrated user with active breakage",
    "profile": ProfileState(
        texture_type="4B",
        texture_label="Dense Coils",
        porosity="high",
        density="high",
        elasticity="low",
        humidity_response="high sensitivity",
        hair_goals=["definition", "length retention"],
        routine_flags=["seal_moisture", "strengthen", "frizz_control"],
    ),
    "env": EnvironmentalContext(
        humidity_level="high",
        heat_stress="high",
        hard_water=False,
        sweat_freq="high",
    ),
    "messages": [
        {"role": "user", "content": "I've been trying everything and my hair just keeps breaking off. Every time I detangle I lose so much hair. I'm so frustrated, I don't know what I'm doing wrong."},
        {"role": "assistant", "content": "I hear you — that sounds really disheartening, especially when you're putting in the effort. Can you tell me more about what your current routine looks like?"},
        {"role": "user", "content": "I deep condition every week, I use a leave-in, but my ends are still snapping. There are short pieces everywhere. I'm starting to think nothing will work for my hair."},
    ],
}


def divider(label: str):
    width = 60
    print(f"\n{'─' * width}")
    print(f"  {label}")
    print(f"{'─' * width}")


def show_bool(value: bool) -> str:
    return "YES" if value else "no"


async def run_demo():
    print("\n" + "=" * 60)
    print("  EMERSON CONCIERGE — AI DECISION WALKTHROUGH")
    print("  For demonstration purposes")
    print("=" * 60)

    profile = SCENARIO["profile"]
    env = SCENARIO["env"]
    messages = SCENARIO["messages"]

    # --- Show the user ---
    divider("WHO WE'RE TALKING TO")
    print(f"  Hair type   : {profile.texture_label} ({profile.texture_type})")
    print(f"  Porosity    : {profile.porosity}")
    print(f"  Density     : {profile.density}")
    print(f"  Elasticity  : {profile.elasticity}")
    print(f"  Climate     : humidity {env.humidity_level}, heat {env.heat_stress}")
    print(f"\n  Last message: \"{messages[-1]['content'][:80]}...\"")

    # --- Step 1: Signal detection ---
    divider("STEP 1  |  What is happening to the hair?")
    print("  Running signal detection...")
    signals_raw = await detect_signals(messages)

    signal_map = {
        "breakage_active":    "Active breakage / shedding",
        "absorption_blocked": "Moisture not absorbing",
        "buildup_present":    "Product / sebum buildup",
        "hold_loss":          "Curls losing definition",
        "coated_feel":        "Waxy or coated texture",
    }
    for key, label in signal_map.items():
        marker = "  ✓" if signals_raw.get(key) else "  ·"
        print(f"{marker}  {label:<30} {show_bool(signals_raw.get(key, False))}")

    if signals_raw.get("evidence_quote"):
        print(f"\n  Evidence    : \"{signals_raw['evidence_quote']}\"")
    print(f"  Confidence  : {signals_raw.get('confidence_score', 0):.0%}")
    print(f"  Fallback    : {'yes' if signals_raw.get('fallback_used') else 'no'}")

    # --- Step 2: Intent detection ---
    divider("STEP 2  |  How is the user engaging?")
    print("  Analysing conversation tone and state...")
    intent_raw = await detect_intent(messages)

    print(f"  Journey state   : {intent_raw['journey_state']}")
    print(f"  Intent clarity  : {intent_raw['intent_clarity']}")
    print(f"  Confidence level: {intent_raw['confidence_level']}")
    print(f"  Friction score  : {intent_raw['friction_score']}")
    print(f"  Emotional state : {intent_raw['emotional_state']}")
    if intent_raw.get("reasoning"):
        print(f"\n  Reasoning   : {intent_raw['reasoning'][:120]}")

    # --- Step 3: Decision Engine ---
    divider("STEP 3  |  What does the hair actually need?")
    print("  Running rules-based decision engine...")

    session_signal = SessionSignal(**{
        k: signals_raw.get(k, False)
        for k in SessionSignal.model_fields
        if k in signals_raw
    })

    from app.services.session_intent.session_intent_service import process_session_intent
    session_intent = await process_session_intent(messages)

    strategy = build_strategy_payload(profile, session_signal, env, session_intent)

    print(f"\n  Decision state  : {strategy.decision_state}")
    print(f"\n  Routine plan    :")
    print(f"    Steps         : {strategy.routine_constraints.step_count_target}")
    print(f"    Must include  : {', '.join(strategy.routine_constraints.mandatory_steps)}")
    print(f"    Must avoid    : {', '.join(strategy.routine_constraints.forbidden_steps)}")
    print(f"\n  Product filters :")
    print(f"    Required      : {', '.join(strategy.product_filters.required_flags)}")
    print(f"    Forbidden     : {', '.join(strategy.product_filters.forbidden_flags)}")
    print(f"    Hold level    : {strategy.product_filters.ideal_hold_level}")
    print(f"    Porosity match: {strategy.product_filters.porosity_match}")

    # --- Step 4: JTE ---
    divider("STEP 4  |  How should we deliver this?")
    print("  Journey Transition Engine calibrating...")

    delivery = resolve_delivery_plan(strategy.jte_input, strategy.decision_state)

    print(f"\n  Readiness score : {delivery.readiness_score}  ({delivery.readiness_band})")
    print(f"  Response mode   : {delivery.response_mode}")
    print(f"  Response depth  : {delivery.response_depth}")
    print(f"  Tone profile    : {delivery.tone_profile}")
    print(f"  CTA pressure    : {delivery.cta_pressure}")
    print(f"  Product exposure: {delivery.product_exposure}")
    print(f"  Ask strategy    : {delivery.ask_strategy}")

    # --- Step 5: Products ---
    candidate_products = []
    if delivery.product_exposure != "hidden":
        divider("STEP 5  |  Finding relevant products")
        print("  Searching Emerson catalogue...")
        filters = strategy.product_filters
        query = " ".join(filters.required_flags + [filters.porosity_match or "", filters.texture_match or ""])
        result = await query_products(query.strip(), top_k=3)
        candidate_products = result.get("products", [])
        print(f"  Found {len(candidate_products)} candidate products")
        for p in candidate_products:
            print(f"    · {p.get('content', '')[:80]}")
    else:
        divider("STEP 5  |  Products")
        print("  JTE decision: not ready for products yet — building trust first.")

    # --- Step 6: Response Composer ---
    divider("STEP 6  |  Composing response")
    print("  Emerson is responding...\n")

    composer_input = ResponseComposerInput(
        strategy_payload=strategy,
        jte_delivery_plan=delivery,
        profile_state=profile,
        candidate_products=candidate_products,
        recent_messages=messages,
    )

    print("  " + "·" * 56)
    async for chunk in compose_response(composer_input):
        if chunk.get("type") == "content":
            print(chunk["content"], end="", flush=True)
    print("\n  " + "·" * 56)

    print("\n" + "=" * 60)
    print("  END OF DEMO")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
