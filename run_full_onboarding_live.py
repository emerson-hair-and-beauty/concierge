import asyncio
import json
import os
import sys

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.api.models import OrchestratorInput
from app.agents.orchestrator import orchestrator

async def run_live_onboarding():
    print("\n" + "="*60)
    print("LIVE ONBOARDING SESSION - STARTING REAL API CALLS")
    print("="*60 + "\n")

    # Real-world payload for Alex
    test_input = OrchestratorInput(
        user_id="live-tester-alex",
        first_name="Alex",
        texture="Curly (Type 3A)",
        density="Medium",
        moisture_behaviour="Normal Porosity",
        humidity_response="Frizz",
        hair_goals=["Definition", "Frizz Control", "Shine"],
        location="Dubai, UAE" # To trigger weather defense scenarios
    )

    print(f"Requesting Live Routine for: {test_input.first_name}")
    print(f"Profile: {test_input.texture}, {test_input.density} density, {test_input.moisture_behaviour}")
    print("-" * 30)

    try:
        async for chunk_str in orchestrator(test_input):
            chunk = json.loads(chunk_str)
            chunk_type = chunk.get("type")
            
            if chunk_type == "status":
                print(f"\n[STATUS] {chunk.get('content')}")
            
            elif chunk_type == "content":
                # Print routine text chunks live
                print(chunk.get("content"), end="", flush=True)
                
            elif chunk_type == "product_recommendation":
                content = chunk.get("content", {})
                print(f"\n\n[RECOMMENDATION] {content.get('step')}")
                print(f"Action: {content.get('action')}")
                print(f"Notes: {content.get('notes')}")
                
                products = content.get("products", [])
                if products:
                    print("Found matching products in catalog:")
                    for p in products:
                        print(f"  - {p['id']}: {p['content'][:100]}...")
                else:
                    print("No products found for this step.")
                    
            elif chunk_type == "token_summary":
                print("\n" + "="*60)
                print("LIVE USAGE & COST REPORT")
                print("="*60)
                summary = chunk["content"]
                
                rg = summary.get("routine_generation", {})
                emb = summary.get("embeddings", {})
                
                print(f"\n[LLM] Model: {rg.get('model')}")
                print(f"  Tokens: {rg.get('total_tokens', 0):,}")
                
                print(f"\n[Embeddings] Model: {emb.get('model')}")
                print(f"  Calls: {emb.get('calls', 0)}")
                print(f"  Tokens: {emb.get('total_tokens', 0):,}")
                
                print(f"\nESTIMATED COST: ${summary.get('estimated_cost_usd', 0.0):.6f}")
                print("-" * 30)
                
            elif chunk_type == "error":
                print(f"\n[ERROR] {chunk.get('content')}")
                if chunk.get("details"):
                    print(f"Details: {chunk.get('details')}")

    except Exception as e:
        print(f"\n!!! FATAL ERROR IN SIMULATION: {str(e)}")

    print("\n" + "="*60)
    print("LIVE ONBOARDING COMPLETE")
    print("="*60 + "\n")

if __name__ == "__main__":
    if not os.path.exists("app/.env"):
        print("Warning: app/.env not found. Ensure GEMINI_API_KEY is in your environment.")
    asyncio.run(run_live_onboarding())
