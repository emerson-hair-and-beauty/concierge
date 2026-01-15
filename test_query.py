import asyncio
import os
import sys

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.agents.recommendation.lib.knowledge_base.query_products import query_products

async def test_query():
    print("Testing query_products...")
    try:
        results = await query_products("gentle cleansing for waves", top_k=2)
        print(f"Results: {results}")
    except Exception as e:
        print(f"Error in query_products: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_query())
