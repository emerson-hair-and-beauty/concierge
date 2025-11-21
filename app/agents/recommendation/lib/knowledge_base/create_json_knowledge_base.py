import csv
import json
import os

# Path to your CSV export (can be relative). The output JSON will be
# written into the same directory as this script to ensure consistent
# placement regardless of the current working directory.
SCRIPT_DIR = os.path.dirname(__file__)
CSV_FILE = os.path.join(SCRIPT_DIR, "products_export_1.csv")
JSON_FILE = os.path.join(SCRIPT_DIR, "product_kb.json")

# Fields we care about for the KB
RELEVANT_FIELDS = [
    "Handle",
    "Title",
    "Variant Price",
    "Ingredients (product.metafields.custom.ingredients)",
    "Complementary products (product.metafields.shopify--discovery--product_recommendation.complementary_products)",
    "How to use (product.metafields.custom.how_to_use)",
    "Tags",
    "Type"  # Needed for filtering
]

products = []

with open(CSV_FILE, newline="", encoding="utf-8") as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        # Skip rows where Type is empty
        if not row.get("Type"):
            continue

        product = {field: row.get(field, "").strip() for field in RELEVANT_FIELDS}
        
        # Convert ingredients into a list (assuming comma-separated)
        if product["Ingredients (product.metafields.custom.ingredients)"]:
            product["Ingredients"] = [
                i.strip() for i in product.pop("Ingredients (product.metafields.custom.ingredients)").split(",")
            ]
        else:
            product["Ingredients"] = []
        
        # Optional: convert related/complementary products into lists
        for key in ["Complementary products (product.metafields.shopify--discovery--product_recommendation.complementary_products)",
                    "Related products (product.metafields.shopify--discovery--product_recommendation.related_products)"]:
            if row.get(key):
                product[key] = [i.strip() for i in row[key].split(",")]
            else:
                product[key] = []

        products.append(product)

# Save to JSON
with open(JSON_FILE, "w", encoding="utf-8") as f:
    json.dump(products, f, indent=2)

print(f"Knowledge base saved to {JSON_FILE}, total products: {len(products)}")
