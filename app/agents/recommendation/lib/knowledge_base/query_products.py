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


from app.pinecone_config import get_pinecone_index
from app.agents.llm_call.provider import embed

async def query_products(query_text, top_k=5):
    """
    Query Pinecone index for top_k most relevant products.
    """
    print(f"--> Querying products for: {query_text[:50]}...")
    try:
        query_vector = await embed(query_text)
        print(f"--> Embedding generated, size: {len(query_vector)}")
    except Exception as e:
        print(f"ERROR in embed: {str(e)}")
        raise e

    # 2️⃣ Query Pinecone (Sync call in Thread)
    try:
        index = get_pinecone_index()
        import asyncio
        result = await asyncio.to_thread(
            index.query,
            vector=query_vector,
            top_k=top_k,
            include_metadata=True
        )
        print(f"--> Pinecone query successful, matches: {len(result.matches)}")
    except Exception as e:
        print(f"ERROR in pinecone query: {str(e)}")
        raise e
    
    # 3️⃣ Format results
    products = []
    for match in result.matches:
        products.append({
            "id": match.id,
            "content": match.metadata.get("content", "")
        })
    
    return {"products": products}


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