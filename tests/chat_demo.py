"""
Emerson Concierge — Interactive Demo
A non-technical stakeholder can type any hair concern and watch the AI think.

Run:
    python tests/chat_demo.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.decision_state.models import ProfileState, EnvironmentalContext
from app.services.session_signal.signal_detector import detect_signals
from app.services.session_intent.intent_detector import detect_intent
from app.services.decision_state.decision_engine import build_strategy_payload
from app.services.decision_state.jte import resolve_delivery_plan
from app.services.decision_state.models import SessionSignal, ResponseComposerInput
from app.services.decision_state.response_composer import compose_response
from app.agents.recommendation.lib.knowledge_base.query_products import query_products
from app.services.decision_state.decision_engine import build_strategy_payload
from app.services.session_intent.session_intent_service import process_session_intent

# ---------------------------------------------------------------------------
# Pick a profile to demo with — swap as needed
# ---------------------------------------------------------------------------

PROFILES = {
    "1": ProfileState(
        texture_type="4B",
        texture_label="Dense Coils",
        porosity="high",
        density="high",
        elasticity="low",
        humidity_response="high sensitivity",
        hair_goals=["length retention", "definition"],
        routine_flags=["seal_moisture", "strengthen", "frizz_control"],
    ),
    "2": ProfileState(
        texture_type="3C",
        texture_label="Tight Curls",
        porosity="low",
        density="medium",
        humidity_response="moderate sensitivity",
        hair_goals=["definition", "moisture"],
        routine_flags=["frizz_control", "avoid_butters", "use_heat_for_masks"],
    ),
    "3": ProfileState(
        texture_type="4A",
        texture_label="Loose Coils",
        porosity="medium",
        density="high",
        humidity_response="low sensitivity",
        hair_goals=["moisture", "scalp health"],
        routine_flags=["standard_care", "seal_moisture"],
    ),
}

ENV = EnvironmentalContext(
    humidity_level="high",
    heat_stress="high",
    hard_water=False,
    sweat_freq="high",
)


def divider(label: str):
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")


def pick_profile() -> ProfileState:
    print("\n" + "=" * 60)
    print("  EMERSON CONCIERGE — INTERACTIVE DEMO")
    print("=" * 60)
    print("\n  Choose a hair profile to demo with:\n")
    print("  [1]  Dense Coils (4B) — High porosity, low elasticity")
    print("  [2]  Tight Curls (3C) — Low porosity, medium density")
    print("  [3]  Loose Coils (4A) — Medium porosity, high density")
    print()

    while True:
        choice = input("  Enter 1, 2, or 3: ").strip()
        if choice in PROFILES:
            profile = PROFILES[choice]
            print(f"\n  Profile selected: {profile.texture_label} ({profile.texture_type})")
            return profile
        print("  Please enter 1, 2, or 3.")


async def run_turn(messages: list, profile: ProfileState):
    divider("WHAT THE AI IS DOING")

    # Step 1
    print("\n  Step 1 — Detecting hair signals...")
    signals_raw = await detect_signals(messages)
    active = [k for k in ["breakage_active", "absorption_blocked", "buildup_present", "hold_loss", "coated_feel"] if signals_raw.get(k)]
    if active:
        print(f"  Active signals : {', '.join(active)}")
    else:
        print(f"  Active signals : none detected")
    if signals_raw.get("evidence_quote"):
        print(f"  Evidence       : \"{signals_raw['evidence_quote']}\"")

    # Step 2
    print("\n  Step 2 — Reading the conversation tone...")
    intent_raw = await detect_intent(messages)
    print(f"  Journey state  : {intent_raw['journey_state']}")
    print(f"  Emotional state: {intent_raw['emotional_state']}")
    print(f"  Friction       : {intent_raw['friction_score']}")

    # Step 3
    print("\n  Step 3 — Decision engine running...")
    session_signal = SessionSignal(**{k: signals_raw.get(k, False) for k in SessionSignal.model_fields if k in signals_raw})
    session_intent = await process_session_intent(messages)
    strategy = build_strategy_payload(profile, session_signal, ENV, session_intent)
    print(f"  Decision state : {strategy.decision_state}")
    print(f"  Routine plan   : {', '.join(strategy.routine_constraints.mandatory_steps)}")

    # Step 4
    print("\n  Step 4 — Journey Transition Engine...")
    delivery = resolve_delivery_plan(strategy.jte_input, strategy.decision_state)
    print(f"  Readiness      : {delivery.readiness_band} (score: {delivery.readiness_score})")
    print(f"  Tone           : {delivery.tone_profile}")
    print(f"  Depth          : {delivery.response_depth}")
    print(f"  Products       : {delivery.product_exposure}")

    # Step 5
    candidate_products = []
    if delivery.product_exposure != "hidden":
        print("\n  Step 5 — Searching product catalogue...")
        from app.services.decision_state.pipeline import _PRODUCT_QUERY_TEMPLATES, _POROSITY_CONTEXT, _TEXTURE_CONTEXT
        base = _PRODUCT_QUERY_TEMPLATES.get(strategy.decision_state or "", "curl care moisturiser")
        porosity_ctx = _POROSITY_CONTEXT.get(strategy.product_filters.porosity_match or "", "")
        texture_ctx = _TEXTURE_CONTEXT.get(strategy.product_filters.texture_match or "", "")
        query = f"{base} {porosity_ctx} {texture_ctx}".strip()
        result = await query_products(query, top_k=3)
        candidate_products = result.get("products", [])
        print(f"  Found {len(candidate_products)} products")
    else:
        print("\n  Step 5 — Products: not surfacing yet (building trust first)")

    # Step 6
    divider("EMERSON'S RESPONSE")
    print()

    composer_input = ResponseComposerInput(
        strategy_payload=strategy,
        jte_delivery_plan=delivery,
        profile_state=profile,
        candidate_products=candidate_products,
        recent_messages=messages[-6:],
    )

    async for chunk in compose_response(composer_input):
        if chunk.get("type") == "content":
            print(chunk["content"], end="", flush=True)

    print("\n")


async def main():
    profile = pick_profile()
    messages = []

    print("\n" + "=" * 60)
    print("  Type your hair concern and press Enter.")
    print("  Type 'quit' to exit.")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Ending demo. Goodbye.")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("\n  Ending demo. Goodbye.")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        await run_turn(messages, profile)

        # Add a placeholder assistant turn so signal detection has context next round
        messages.append({"role": "assistant", "content": "[response delivered]"})


if __name__ == "__main__":
    asyncio.run(main())
