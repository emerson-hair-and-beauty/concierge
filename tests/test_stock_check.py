"""
The stock check removes sold-out products, and never removes a product without a clear answer.

Why: a guest must not get a product they cannot buy. But a slow or blocked shop must
not empty the product list either, so a product without a clear answer stays.

Run from the project root: python tests/test_stock_check.py
"""
import asyncio
import sys

sys.path.insert(0, ".")
from app.services.decision_state import stock_check


def product(sku):
    return {"id": sku, "metadata": {"sku": sku, "product_url": f"https://shop.example/products/{sku}"}}


ANSWERS = {"IN-1": True, "OUT-1": False, "NO-ANSWER": None, "IN-2": True}


async def fake_check(client, p):
    return ANSWERS[p["id"]]


DATA = {"available": True, "variants": [{"sku": "A-8OZ", "available": False}, {"sku": "A-2OZ", "available": True}]}

if __name__ == "__main__":
    stock_check._check = fake_check
    kept = [p["id"] for p in asyncio.run(stock_check.in_stock([product(s) for s in ANSWERS]))]
    CASES = [
        ("sold out removed, no answer kept, order kept", kept, ["IN-1", "NO-ANSWER", "IN-2"]),
        ("the size with the SKU decides, not the whole product", stock_check._available(DATA, "A-8OZ"), False),
        ("another size of the same product is in stock", stock_check._available(DATA, "A-2OZ"), True),
        ("no size with the SKU: the whole product decides", stock_check._available(DATA, "OTHER"), True),
    ]
    failed = 0
    for label, got, want in CASES:
        ok = got == want
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"\n      got  {got}\n      want {want}"))
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)
