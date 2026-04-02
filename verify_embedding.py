from google import genai
import os
import sys
import asyncio

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
from app.config import GEMINI_API_KEY
from google import genai

async def verify_embedding_model(model_name):
    print(f"\n--- Testing Embedding Model: {model_name} ---")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Test single embed_content
    try:
        print(f"Testing single embed_content...")
        response = await client.aio.models.embed_content(
            model=model_name,
            contents="Hello world"
        )
        print(f"✅ Single embed successful. Vector size: {len(response.embeddings[0].values)}")
    except Exception as e:
        print(f"❌ Single embed failed: {str(e)}")

    # Test batch_embed_content (by passing a list)
    try:
        print(f"Testing batch_embed_content (list input)...")
        response = await client.aio.models.embed_content(
            model=model_name,
            contents=["Hello world", "Goodbye world"]
        )
        print(f"✅ Batch embed successful. Vectors: {len(response.embeddings)}")
    except Exception as e:
        print(f"❌ Batch embed failed: {str(e)}")

async def main():
    # Test common embedding models
    models_to_test = [
        "models/gemini-embedding-001",
        "models/gemini-embedding-001"
    ]
    
    for m in models_to_test:
        await verify_embedding_model(m)

if __name__ == "__main__":
    asyncio.run(main())
