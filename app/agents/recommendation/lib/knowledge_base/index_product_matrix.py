"""
Re-indexes the Emerson product catalogue from the Product Matrix Excel file.
- Source  : Summary sheet (per-product flags, metadata, usage context)
- Embeddings : provider.embed() — respects LLM_PROVIDER setting @ 384 dims
- Destination: Pinecone index (replaces all existing vectors)

Run from the project root:
    python app/agents/recommendation/lib/knowledge_base/index_product_matrix.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../")))

import openpyxl
from app.agents.llm_call.provider import embed
from app.pinecone_config import get_pinecone_index

EXCEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../../../../Emerson Product Matrix_Master_File_Updated (1).xlsx"
)

# ---------------------------------------------------------------------------
# Column index map (0-based, from Summary sheet row 7 headers)
# ---------------------------------------------------------------------------
COL = {
    "sku":              1,
    "brand":            2,
    "name":             3,
    "category":         4,
    "price":            5,
    "primary_focus":    7,
    "hold":             8,
    "porosity":         9,
    "density":          10,
    "climate":          11,
    "buildup_risk":     12,
    "aloe":             13,
    "coconut":          14,
    "protein":          15,
    "humectant_heavy":  16,
    "butter_oil_heavy": 17,
    "cg_approved":      18,
    "silicone_free":    19,
    "sulfate_free":     20,
    "beginner_friendly":21,
    "advanced_user":    22,
    "best_used_when":   23,
    "not_ideal_if":     24,
    "hero_use_case":    25,
    "pairs_well_with":  26,
    "alternatives":     27,
    "best_seller":      28,
}


def _yes(val) -> bool:
    return str(val).strip().lower() == "yes" if val else False


def _normalise_porosity(val: str) -> list[str]:
    if not val or str(val).strip().lower() == "all":
        return ["low", "medium", "high"]
    val = str(val).strip().lower()
    mapping = {
        "low":           ["low"],
        "medium":        ["medium"],
        "high":          ["high"],
        "low - medium":  ["low", "medium"],
        "medium - high": ["medium", "high"],
        "low-medium":    ["low", "medium"],
        "medium-high":   ["medium", "high"],
    }
    return mapping.get(val, ["low", "medium", "high"])


def _normalise_density(val: str) -> list[str]:
    if not val or str(val).strip().lower() == "all":
        return ["fine", "medium", "thick"]
    val = str(val).strip().lower()
    mapping = {
        "fine":           ["fine"],
        "medium":         ["medium"],
        "thick":          ["thick"],
        "medium-thick":   ["medium", "thick"],
        "medium - thick": ["medium", "thick"],
    }
    return mapping.get(val, ["fine", "medium", "thick"])


def _build_flags(row_vals: dict) -> list[str]:
    """Converts boolean columns to a searchable flags list for Pinecone metadata filtering."""
    flags = []
    if _yes(row_vals.get("cg_approved")):       flags.append("cg_approved")
    if _yes(row_vals.get("silicone_free")):      flags.append("silicone_free")
    if _yes(row_vals.get("sulfate_free")):       flags.append("sulfate_free")
    if _yes(row_vals.get("beginner_friendly")):  flags.append("beginner_friendly")
    if _yes(row_vals.get("protein")):            flags.append("protein")
    if _yes(row_vals.get("humectant_heavy")):    flags.append("humectant_heavy")
    if _yes(row_vals.get("butter_oil_heavy")):   flags.append("butter_oil_heavy")
    if _yes(row_vals.get("aloe")):               flags.append("aloe")
    if _yes(row_vals.get("coconut")):            flags.append("coconut")
    if _yes(row_vals.get("best_seller")):        flags.append("best_seller")
    if _yes(row_vals.get("advanced_user")):      flags.append("advanced_user")
    if not _yes(row_vals.get("buildup_risk")):   flags.append("low_buildup_risk")
    if not _yes(row_vals.get("humectant_heavy")): flags.append("humectant_safe")
    if not _yes(row_vals.get("butter_oil_heavy")): flags.append("lightweight")
    return flags


def _build_content(row_vals: dict) -> str:
    """Builds a human-readable content string for semantic embedding."""
    parts = [
        f"{row_vals.get('name', '')} by {row_vals.get('brand', '')}.",
        f"Category: {row_vals.get('category', '')}.",
        f"Primary focus: {row_vals.get('primary_focus', '')}.",
        f"Hold level: {row_vals.get('hold', 'None')}.",
        f"Best for porosity: {row_vals.get('porosity', 'All')}.",
        f"Best for density: {row_vals.get('density', 'All')}.",
        f"Climate performance: {row_vals.get('climate', '')}.",
    ]
    if row_vals.get("hero_use_case"):
        parts.append(f"Hero use case: {row_vals['hero_use_case']}.")
    if row_vals.get("best_used_when"):
        parts.append(f"Best used when: {row_vals['best_used_when']}.")
    if row_vals.get("not_ideal_if"):
        parts.append(f"Not ideal if: {row_vals['not_ideal_if']}.")
    if row_vals.get("pairs_well_with"):
        parts.append(f"Pairs well with: {row_vals['pairs_well_with']}.")

    attrs = []
    if _yes(row_vals.get("protein")):            attrs.append("contains protein")
    if _yes(row_vals.get("cg_approved")):        attrs.append("CG approved")
    if _yes(row_vals.get("silicone_free")):      attrs.append("silicone free")
    if _yes(row_vals.get("sulfate_free")):       attrs.append("sulfate free")
    if _yes(row_vals.get("humectant_heavy")):    attrs.append("humectant heavy")
    if _yes(row_vals.get("butter_oil_heavy")):   attrs.append("butter and oil heavy")
    if not _yes(row_vals.get("buildup_risk")):   attrs.append("low buildup risk")
    if _yes(row_vals.get("beginner_friendly")):  attrs.append("beginner friendly")
    if attrs:
        parts.append("Attributes: " + ", ".join(attrs) + ".")

    return " ".join(parts)


def load_products_from_excel(path: str) -> list[dict]:
    print(f"[Indexer] Reading: {path}")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Summary"]

    products = []
    for row in ws.iter_rows(min_row=8, values_only=True):
        sku = row[COL["sku"]] if len(row) > COL["sku"] else None
        if not sku or str(sku).startswith("="):
            continue

        row_vals = {key: (row[idx] if len(row) > idx else None) for key, idx in COL.items()}

        content = _build_content(row_vals)
        flags = _build_flags(row_vals)
        porosity_list = _normalise_porosity(str(row_vals.get("porosity") or "All"))
        density_list = _normalise_density(str(row_vals.get("density") or "All"))

        products.append({
            "id":      str(sku).strip(),
            "content": content,
            "metadata": {
                "content":       content,
                "sku":           str(sku).strip(),
                "brand":         str(row_vals.get("brand") or ""),
                "name":          str(row_vals.get("name") or ""),
                "category":      str(row_vals.get("category") or ""),
                "primary_focus": str(row_vals.get("primary_focus") or ""),
                "hold":          str(row_vals.get("hold") or "None").lower(),
                "porosity":      porosity_list,
                "density":       density_list,
                "flags":         flags,
            }
        })

    print(f"[Indexer] Loaded {len(products)} products from Summary sheet.")
    return products


async def embed_products(products: list[dict]) -> list[dict]:
    from app.config import LLM_PROVIDER
    print(f"[Indexer] Generating embeddings ({LLM_PROVIDER}) for {len(products)} products...")
    for i, product in enumerate(products):
        product["vector"] = await embed(product["content"])
        if (i + 1) % 10 == 0:
            print(f"[Indexer]   {i + 1}/{len(products)} embedded...")
    print(f"[Indexer] All embeddings generated.")
    return products


def upsert_to_pinecone(products: list[dict], batch_size: int = 50):
    index = get_pinecone_index()

    # Delete all existing vectors before re-indexing
    print("[Indexer] Clearing existing index...")
    index.delete(delete_all=True)
    print("[Indexer] Index cleared.")

    batch = []
    for product in products:
        batch.append({
            "id":       product["id"],
            "values":   product["vector"],
            "metadata": product["metadata"],
        })
        if len(batch) >= batch_size:
            index.upsert(batch)
            batch = []

    if batch:
        index.upsert(batch)

    print(f"[Indexer] Upserted {len(products)} products to Pinecone.")


async def main():
    products = load_products_from_excel(EXCEL_PATH)
    if not products:
        print("[Indexer] No products found. Check the file path and sheet structure.")
        return
    products = await embed_products(products)
    upsert_to_pinecone(products)
    print("[Indexer] Done.")


if __name__ == "__main__":
    asyncio.run(main())
