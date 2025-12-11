# query_products.py

import sys
import os

# --- MORE ROBUST PATH FIX START ---

# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Iterate upwards until we find the project root (the directory that contains 'app')
project_root = current_dir
while not os.path.exists(os.path.join(project_root, 'app')):
    # Go up one level
    parent_dir = os.path.dirname(project_root)
    if parent_dir == project_root:
        # We've reached the system root and didn't find 'app'
        print("Error: Could not find 'app' package root.")
        # If this happens, your file structure is likely different than assumed.
        break
    project_root = parent_dir
    
# Add the directory containing 'app' to sys.path
sys.path.append(project_root)

# --- MORE ROBUST PATH FIX END ---


from app.pinecone_config import index, DIMENSION 
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def query_products(query_text, top_k=5):
    """
    Query Pinecone index for top_k most relevant products.
    
    Args:
        query_text (str): The user's natural language query.
        top_k (int): Number of results to return.
    
    Returns:
        List of dicts with 'id' and 'content'.
    """
    # 1️⃣ Encode query
    query_vector = model.encode(query_text).tolist()
    
    # 2️⃣ Query Pinecone
    result = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True
    )
    
    # 3️⃣ Format results
    products = []
    for match in result.matches:
        products.append({
            "id": match.id,
            "content": match.metadata.get("content", "")
        })
    
    return products


# -----------------------------# Example usage
# if __name__ == "__main__":
#     user_query = "Best conditioner for dry curly hair"
#     results = query_products(user_query, top_k=5)
#     
#     print(f"\nTop {len(results)} results for query: '{user_query}'\n")
#     for i, prod in enumerate(results, 1):
#         print(f"{i}. ID: {prod['id']}")
#         print(f"   Product Info: {prod['content'][:300]}...")  # show first 300 chars
#         print()
# -----------------------------