"""
Stock check: remove sold-out products before the concierge shows them.

The shop gives live stock for each product to the public: add ".js" to a product
page link, and Shopify sends back the product data. Each size has an `available`
field, which Shopify sets to false when the stock for that size is 0.

Rules:
- The check asks the shop about all products at the same time, so the guest waits
  only for the slowest answer.
- Each answer is kept for CACHE_SECONDS, so the shop does not block repeated checks.
- If the shop does not answer, the product stays. A stock check never stops a reply.
"""
import asyncio
import ssl
import time
from typing import Dict, List, Optional, Tuple

import httpx

CACHE_SECONDS = 15 * 60
TIMEOUT_SECONDS = 2.5

# The secure connection settings take about 0.5 seconds to build, so build them one time.
_SSL = ssl.create_default_context()

# SKU -> (in stock, the time of the check). Lives in memory, like the chat history.
_cache: Dict[str, Tuple[bool, float]] = {}


def _available(data: dict, sku: str) -> bool:
    """The size with this SKU, or the whole product when no size has the SKU."""
    for variant in data.get("variants") or []:
        if variant.get("sku") == sku:
            return bool(variant.get("available"))
    return bool(data.get("available", True))


async def _check(client: httpx.AsyncClient, product: dict) -> Optional[bool]:
    """True or False from the shop, or None when the shop gives no clear answer."""
    metadata = product.get("metadata") or {}
    sku = metadata.get("sku") or product.get("id") or ""
    url = (metadata.get("product_url") or "").split("?")[0]
    if not url:
        return None
    cached = _cache.get(sku)
    if cached and time.monotonic() - cached[1] < CACHE_SECONDS:
        return cached[0]
    try:
        response = await client.get(url + ".js")
        response.raise_for_status()
        in_stock = _available(response.json(), sku)
    except Exception as e:
        print(f"[Stock] No answer for {sku}, the product stays: {e}")
        return None
    _cache[sku] = (in_stock, time.monotonic())
    return in_stock


async def in_stock(products: List[dict]) -> List[dict]:
    """The same products in the same order, without the ones the shop says are sold out."""
    if not products:
        return products
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=True, verify=_SSL) as client:
        answers = await asyncio.gather(*(_check(client, p) for p in products))
    sold_out = [p.get("id") for p, a in zip(products, answers) if a is False]
    if sold_out:
        print(f"[Stock] Sold out, not shown: {sold_out}")
    return [p for p, a in zip(products, answers) if a is not False]
