"""
The composer shows one product on every selective turn. That cut the expert's
shampoo-and-conditioner pairs down to the shampoo alone. These tests pin the
new wider exposure: a selective turn sees up to three products.

Run from the project root: python tests/test_product_exposure.py
"""
import sys

sys.path.insert(0, ".")

from app.services.decision_state.models import (
    JTEInput,
    JTEDeliveryPlan,
    ProfileState,
    ResponseComposerInput,
    StrategyPayload,
)
from app.services.decision_state.response_composer import _build_products_section


def make_input(exposure, product_count=5):
    payload = StrategyPayload(jte_input=JTEInput(
        journey_state="diagnosing",
        intent_clarity="medium",
        confidence_level="unsure",
        friction_score="moderate",
        emotional_state="neutral",
    ))
    plan = JTEDeliveryPlan(
        response_mode="educate",
        response_depth="medium",
        cta_pressure="soft",
        product_exposure=exposure,
        tone_profile="expert_calm",
        ask_strategy="no_question",
        readiness_band="medium",
        readiness_score=3,
    )
    return ResponseComposerInput(
        strategy_payload=payload,
        jte_delivery_plan=plan,
        profile_state=ProfileState(
            texture_type="3C", texture_label="Tight Curls",
            porosity="low", density="medium",
        ),
        candidate_products=[{"content": f"Product {i}"} for i in range(product_count)],
    )


def count_products(exposure, product_count=5):
    section = _build_products_section(make_input(exposure, product_count))
    return sum(1 for line in section.splitlines() if line.startswith("- "))


CASES = [
    ("selective shows three products, not one", count_products("selective"), 3),
    ("direct shows all products", count_products("direct"), 5),
    ("hidden shows no products", count_products("hidden"), 0),
    ("routine_led shows all products", count_products("routine_led"), 5),
    ("a short list shows what exists, not three blanks", count_products("selective", product_count=2), 2),
]

if __name__ == "__main__":
    failed = 0
    for label, got, want in CASES:
        ok = got == want
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"\n      got  {got}\n      want {want}"))
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)
