"""
The curl expert's first-choice rules for buildup and scalp products.

Why: a product with "clarifying" in its name is not always the right reset product,
and the search alone picked one by its name. The expert sets the first products:
- Buildup on the hair: a Detox product that is a shampoo or cleanser, then the other Detox products.
- Buildup on the scalp: the As I Am Dry & Itchy Scalp Care shampoo and conditioner, then the other Detox products.
- A sensitive scalp: the As I Am Dry & Itchy Scalp Care shampoo and conditioner only.

Run from the project root: python tests/test_first_choice_products.py
"""
import sys

sys.path.insert(0, ".")
from app.services.decision_state.pipeline import _first_choice_products, _mentions_scalp


def product(name, category):
    return {"id": name, "metadata": {"name": name, "category": category}}


CATALOG = [
    product("Innersense Detox Hair Mask", "Detox"),
    product("Innersense Detox Hair Mask (2 oz)", "Detox"),
    product("Miche Detox Gentle Clarifying Shampoo", "Detox"),
    product("Some Brand Clarifying Shampoo", "Cleanser"),          # "clarifying" in the name, but not Detox
    product("As I Am Dry & Itchy Scalp Care Conditioner", "Instant Conditioner"),
    product("As I Am Dry & Itchy Scalp Care Leave-in Conditioner", "Leave In"),
    product("As I Am Dry & Itchy Scalp Care Shampoo", "Cleanser"),
]


def names(path, scalp):
    return [p["id"] for p in _first_choice_products(CATALOG, path, scalp)]


CASES = [
    ("hair buildup: Detox shampoo first, then masks, one size each, no name-only clarifier",
     names("reset_first", False),
     ["Miche Detox Gentle Clarifying Shampoo", "Innersense Detox Hair Mask"]),
    ("scalp buildup: As I Am shampoo, conditioner, then Detox non-shampoos",
     names("reset_first", True),
     ["As I Am Dry & Itchy Scalp Care Shampoo", "As I Am Dry & Itchy Scalp Care Conditioner",
      "Innersense Detox Hair Mask"]),
    ("sensitive scalp: As I Am shampoo and conditioner only, no leave-in, no detox",
     names("scalp_calm_first", False),
     ["As I Am Dry & Itchy Scalp Care Shampoo", "As I Am Dry & Itchy Scalp Care Conditioner"]),
    ("the guest's words decide scalp",
     [_mentions_scalp([{"role": "user", "content": "My SCALP feels coated"}]),
      _mentions_scalp([{"role": "user", "content": "my curls feel coated"},
                       {"role": "assistant", "content": "Is it your scalp?"}])],
     [True, False]),
]

if __name__ == "__main__":
    failed = 0
    for label, got, want in CASES:
        ok = got == want
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"\n      got  {got}\n      want {want}"))
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)
