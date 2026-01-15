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
from app.config import GEMINI_API_KEY
from google import genai

async def query_products(query_text, top_k=5):
    """
    Query Pinecone index for top_k most relevant products.
    """
    print(f"--> Quering products for: {query_text[:50]}...")
    # 1️⃣ Encode query using Gemini API (Async)
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = await client.aio.models.embed_content(
            model="text-embedding-004",
            contents=query_text,
            config={
                "output_dimensionality": 384
            }
        )
        print(f"DEBUG: Response object: {response}")
        # print(f"DEBUG: Response keys/dir: {dir(response)}")
        if hasattr(response, 'usage_metadata'):
             print(f"DEBUG: usage_metadata: {response.usage_metadata}")
             
        query_vector = response.embeddings[0].values
        print(f"--> Embedding generated, size: {len(query_vector)}")
    except Exception as e:
        print(f"ERROR in embed_content: {str(e)}")
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
    
    # Extract usage if available
    embedding_usage = {
        "model": "text-embedding-004",
        "usage": {
            "prompt_tokens": 0,
            "total_tokens": 0
        }
    }
    
    if response and hasattr(response, 'usage_metadata') and response.usage_metadata:
        embedding_usage["usage"]["prompt_tokens"] = response.usage_metadata.prompt_token_count
        embedding_usage["usage"]["total_tokens"] = response.usage_metadata.total_token_count

    return {
        "products": products,
        "embedding_usage": embedding_usage
    }


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