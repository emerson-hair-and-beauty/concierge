import json
from sentence_transformers import SentenceTransformer
from app.pinecone_config import index, DIMENSION
import os

BASE_DIR = os.path.dirname(__file__)
PRODUCT_JSON = os.path.join(BASE_DIR, "product_kb.json")
PRODUCT_VECTORS_JSON = os.path.join(BASE_DIR, "product_vectors.json")


# -----------------------------
# 1. Load and preprocess products
# -----------------------------
def load_products(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    preprocessed = []
    for i, p in enumerate(products):
        title = p.get("Title", "")
        ingredients = ", ".join(p.get("Ingredients", []))
        how_to_use = p.get("How to use (product.metafields.custom.how_to_use)", "")
        tags = p.get("Tags", "")
        hair_finish = p.get("Hair care finish (product.metafields.shopify.hair-care-finish)", "")
        hold_level = p.get("Hold level (product.metafields.shopify.hold-level)", "")
        complementary = ", ".join(
            p.get(
                "Complementary products (product.metafields.shopify--discovery--product_recommendation.complementary_products)",
                []
            )
        )

        content = (
            f"{title}. Ingredients: {ingredients}. How to use: {how_to_use}. "
            f"Tags: {tags}. Hair finish: {hair_finish}. Hold level: {hold_level}. "
            f"Complementary products: {complementary}"
        )

        preprocessed.append({
            "id": str(i),
            "content": content
        })
    return preprocessed

# -----------------------------
# 2. Generate embeddings
# -----------------------------
def generate_embeddings(products, model_name="all-MiniLM-L6-v2"):
    model = SentenceTransformer(model_name)
    for p in products:
        p["vector"] = model.encode(p["content"]).tolist()
    return products

# -----------------------------
# 3. Save embeddings locally
# -----------------------------
def save_embeddings(products, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2)
    print(f"✅ Saved {len(products)} embeddings to {out_file}")

# -----------------------------
# 4. Upsert to Pinecone
# -----------------------------
def upsert_to_pinecone(products, batch_size=50):
    upsert_items = []

    for p in products:
        upsert_items.append({
            "id": p["id"],
            "values": p["vector"],  # REQUIRED
            "metadata": {"content": p["content"]}
        })

        if len(upsert_items) >= batch_size:
            index.upsert(upsert_items)
            upsert_items = []

    # Upsert remaining
    if upsert_items:
        index.upsert(upsert_items)

    print(f"✅ Successfully upserted {len(products)} products into Pinecone index '{index.name}'")

# -----------------------------
# 5. Main workflow
# -----------------------------
if __name__ == "__main__":
    products = load_products(PRODUCT_JSON)
    products = generate_embeddings(products)
    save_embeddings(products, PRODUCT_VECTORS_JSON)
    upsert_to_pinecone(products)