"""Score real composer output with the tone model, so you can judge the ranking yourself.

Every check so far has been circular: the off-brand corpus, the model trained on
it, and the test sentences used to praise it all came from the same head. A model
can look excellent on text written to make it look excellent.

This runs the actual pipeline instead. Real prompts, real generations, real
scores — printed in full so the only question left is the one that matters: does
the reply Simasia put first actually read better than the one it put last?

Nothing here is asserted automatically. The point is to put real output in front
of a person, because "sounds like Emerson" is not a thing a test can decide.

Cost: scenarios x candidates generations, plus one embedding each.

Usage:
    python scripts/evaluate_tone_ranking.py
    python scripts/evaluate_tone_ranking.py --candidates 5 --scenario climate
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services import tone_guard  # noqa: E402
from app.services.decision_state.jte import resolve_delivery_plan  # noqa: E402
from app.services.decision_state.models import (  # noqa: E402
    EnvironmentalContext,
    JTEInput,
    ProductFilters,
    ProfileState,
    ResponseComposerInput,
    StrategyPayload,
    TextureModifiers,
)
from app.services.decision_state.response_composer import (  # noqa: E402
    CANDIDATE_TEMPERATURE,
    _collect,
    render_response_prompt,
)


def _texture(label: str = "medium") -> TextureModifiers:
    return TextureModifiers(
        shrinkage_factor=label, fragility_index=label, definition_difficulty=label, label=label
    )


def _scenario(
    *,
    decision_state: str,
    message: str,
    journey: str,
    clarity: str = "medium",
    confidence: str = "unsure",
    friction: str = "moderate",
    emotion: str = "neutral",
    porosity: str = "high",
    env: EnvironmentalContext | None = None,
) -> ResponseComposerInput:
    """Build composer input the way production does: describe the customer, derive the plan.

    A scenario says who is asking and what state they routed to. It does not get
    to pick the voice — `resolve_delivery_plan` does that, from the same inputs
    the live pipeline uses.

    This used to hand-write the `JTEDeliveryPlan`, and every scenario reviewed a
    voice the pipeline cannot emit: `reset_first` was tested as
    troubleshoot/medium/expert_calm where production sends educate/long/
    warm_reassuring. The `JTEInput` was junk too (`journey_state="exploring"`,
    `intent_clarity="clear"` — neither is in the enum), so `readiness_score` came
    out 0 every time. Both are fixed by deriving instead of declaring.

    The five intent fields must be real enum values from `SessionIntent`; anything
    else scores zero and silently drags readiness to `low`.
    """
    jte_input = JTEInput(
        journey_state=journey,
        intent_clarity=clarity,
        confidence_level=confidence,
        friction_score=friction,
        emotional_state=emotion,
    )
    return ResponseComposerInput(
        strategy_payload=StrategyPayload(
            decision_state=decision_state,
            product_filters=ProductFilters(texture_modifiers=_texture()),
            jte_input=jte_input,
        ),
        jte_delivery_plan=resolve_delivery_plan(jte_input, decision_state),
        profile_state=ProfileState(
            texture_type="3B",
            texture_label="curly",
            porosity=porosity,
            density="medium",
            humidity_response="frizzes",
            routine_flags=[],
        ),
        env=env,
        candidate_products=[],
        recent_messages=[{"role": "user", "content": message}],
    )


# Every entry here was migrated in one edit when the settings bug was fixed. A
# half-migrated SCENARIOS, where some keys derive their plan and others declare
# it, is worse than either end state: the mislabelled ones look identical.
#
# Verdicts recorded before that migration are still valid as a wording
# comparison — both arms of the ed7cedf1db2a vs 847425ed0fc1 test used the same
# wrong settings — but the per-setting rows in `reviews.py stats` from those
# batches are mislabelled and should not be read.
SCENARIOS = {
    "breakage": _scenario(
        decision_state="repair_first",
        journey="diagnosing",
        message=(
            "my hair keeps snapping when i detangle and theres little broken pieces "
            "all over my shoulders"
        ),
    ),
    "buildup": _scenario(
        decision_state="reset_first",
        journey="troubleshooting",
        message="my curls have gone limp and my leave-in just sits on top of my hair now",
        porosity="low",
    ),
    # Same chain as "buildup" (reset_first), deliberately different customer
    # wording. That pairing scored 2 out of 2 with the brand expert, and a second
    # question through it is what separates "these instructions work" from "that
    # one question was easy". Without this, a good result on buildup alone proves
    # nothing about the instructions.
    "coated": _scenario(
        decision_state="reset_first",
        journey="troubleshooting",
        message="everything i put on my hair feels like it just sits there and my curls feel heavy and dull",
        porosity="low",
    ),
    "climate": _scenario(
        decision_state="climate_control_first",
        journey="diagnosing",
        message="my definition is gone by lunchtime every day here in Dubai",
        env=EnvironmentalContext(
            humidity_level="high", heat_stress="high", ac_exposure="high", hard_water=True
        ),
    ),
    "frustrated": _scenario(
        decision_state="simplify_and_reduce_friction",
        journey="troubleshooting",
        clarity="low",
        confidence="overwhelmed",
        friction="high",
        emotion="frustrated",
        message="ive tried everything and nothing works, im honestly ready to just cut it all off",
    ),
}


async def run(name: str, composer_input: ResponseComposerInput, n: int) -> None:
    prompt = render_response_prompt(composer_input)
    results = await asyncio.gather(
        *(_collect(prompt, CANDIDATE_TEMPERATURE) for _ in range(n)),
        return_exceptions=True,
    )

    texts = [t for r in results if not isinstance(r, BaseException) for t, _ in [r] if t.strip()]
    failed = sum(1 for r in results if isinstance(r, BaseException))

    print(f"\n{'=' * 78}")
    print(f"SCENARIO: {name}")
    print(f"  user says      : {composer_input.recent_messages[0]['content']}")
    plan = composer_input.jte_delivery_plan
    print(f"  decision state : {composer_input.strategy_payload.decision_state}")
    print(f"  tone / depth   : {plan.tone_profile} / {plan.response_depth}")
    print(f"{'=' * 78}")

    if not texts:
        print(f"  all {n} generations failed")
        return
    if failed:
        print(f"  ({failed} of {n} generations failed)")

    scored = sorted(((tone_guard.score(t), t) for t in texts), key=lambda p: -(p[0] or 0))

    for rank, (score, text) in enumerate(scored, 1):
        marker = "  <-- SHIPPED" if rank == 1 else ""
        label = f"{score:.3f}" if score is not None else "  n/a"
        print(f"\n  [{rank}] score {label}{marker}")
        for line in text.strip().splitlines():
            if line.strip():
                print(f"      {line.strip()}")

    values = [s for s, _ in scored if s is not None]
    if len(values) > 1:
        print(f"\n  spread across candidates: {max(values) - min(values):.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score real composer output.")
    parser.add_argument("--candidates", type=int, default=4)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default=None)
    args = parser.parse_args()

    if not tone_guard.is_available():
        print("Tone model unavailable — nothing to evaluate.")
        return 1

    chosen = {args.scenario: SCENARIOS[args.scenario]} if args.scenario else SCENARIOS
    for name, composer_input in chosen.items():
        asyncio.run(run(name, composer_input, args.candidates))

    print(
        "\n\nRead the replies, not the numbers. The question is whether [1] is\n"
        "genuinely better than the last one. If the ordering looks arbitrary, the\n"
        "model is not ready to gate anything — regardless of what it scored.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
