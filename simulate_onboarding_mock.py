import asyncio
import json
import os
import sys
from unittest.mock import patch, MagicMock

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.api.models import OrchestratorInput
from app.agents.orchestrator import orchestrator

# --- 1. MOCK DATA DEFINITIONS ---

MOCK_ROUTINE = {
    "routine": [
        {
            "step": "Clarifying Wash",
            "action": "Wash with a clarifying shampoo to reset the hair surface and remove buildup.",
            "ingredients": ["Sodium Laureth Sulfate", "C14-16 Olefin Sulfonate"],
            "notes": "Focus on the scalp. Use only once every 4 weeks."
        },
        {
            "step": "Conditioning",
            "action": "Apply a rich, slip-heavy conditioner to detangle and infuse moisture.",
            "ingredients": ["Cetearyl Alcohol", "Behentrimonium Methosulfate", "Glycerin"],
            "notes": "Detangle with fingers while hair is soaking wet."
        },
        {
            "step": "Styling",
            "action": "Layer a moisturizing leave-in under a strong-hold gel for definition.",
            "ingredients": ["Polyquaternium-69", "Aloe Barbadensis Leaf Juice"],
            "notes": "Scrunch upwards to encourage curl formation."
        }
    ]
}

MOCK_PRODUCTS = [
    {"id": "gid://shopify/Product/111", "content": "Emerson Reset Shampoo - Deep cleansing without stripping."},
    {"id": "gid://shopify/Product/222", "content": "Emerson Silk Conditioner - Ultimate detangling and hydration."},
    {"id": "gid://shopify/Product/333", "content": "Emerson Define Gel - Strong hold and frizz protection."}
]

# --- 2. MOCK FUNCTIONS ---

async def mock_generate_routine(advice):
    """Mocks the LLM routine generation stream."""
    # Simulate a stream of content
    routine_str = json.dumps(MOCK_ROUTINE)
    
    # Send content in chunks
    chunk_size = 50
    for i in range(0, len(routine_str), chunk_size):
        yield {"type": "content", "content": routine_str[i:i+chunk_size]}
        await asyncio.sleep(0.01) # Small delay for realism
        
    # Send mock usage
    yield {
        "type": "token_usage", 
        "usage": {"prompt_tokens": 500, "completion_tokens": 300, "total_tokens": 800}
    }

async def mock_query_products(query_text, top_k=5):
    """Mocks the Pinecone/Gemini embedding product search."""
    return {
        "products": MOCK_PRODUCTS[:2], # Return top 2 matching products
        "embedding_usage": {
            "model": "gemini-embedding-001",
            "usage": {"prompt_tokens": 50, "total_tokens": 50}
        }
    }

# --- 3. THE SIMULATION ---

async def simulate_mock_onboarding():
    print("\n" + "="*60)
    print("MOCK ONBOARDING SIMULATION (ZERO API COST)")
    print("="*60 + "\n")

    # Generic Payload
    test_input = OrchestratorInput(
        user_id="mock-user-001",
        first_name="Alex",
        texture="Curly (Type 3)",
        density="Medium",
        moisture_behaviour="Medium Porosity",
        hair_goals=["Definition", "Frizz Control"]
    )

    # Patch the real API calls with our mocks
    with patch("app.agents.orchestrator.generateRoutine", side_effect=mock_generate_routine), \
         patch("app.agents.orchestrator.collateAdvice", return_value={"goals": "Generic Goals", "directives": {}, "routine_flags": {}}), \
         patch("app.agents.recommendation.lib.create_recommendations.query_products", side_effect=mock_query_products):
        
        print(f"Requesting routine for: {test_input.first_name}...")
        
        async for chunk_str in orchestrator(test_input):
            try:
                chunk = json.loads(chunk_str)
                chunk_type = chunk.get("type")
                
                if chunk_type == "status":
                    print(f"[{chunk_type.upper()}] {chunk.get('content')}")
                elif chunk_type == "content":
                    # We skip printing raw routine JSON for brevity unless it's the end
                    pass
                elif chunk_type == "product_recommendation":
                    content = chunk.get("content", {})
                    print(f"\n--- STEP: {content.get('step')} ---")
                    print(f"Action: {content.get('action')}")
                    for p in content.get("products", []):
                        print(f"  🛒 PRODUCT ID: {p['id']}")
                        print(f"     Description: {p['content'][:100]}...")
                elif chunk_type == "token_summary":
                    print("\n" + "-"*30)
                    print("MOCK USAGE REPORT:")
                    print(json.dumps(chunk["content"], indent=2))
                    print("-"*30)
                elif chunk_type == "error":
                    print(f"!!! ERROR: {chunk.get('content')}")
            except Exception as e:
                print(f"Parsing error: {e} | Chunk: {chunk_str[:50]}")

    print("\n" + "="*60)
    print("SIMULATION COMPLETE")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(simulate_mock_onboarding())
