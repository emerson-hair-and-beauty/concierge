import asyncio
import sys
import os
import json
import time

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.agents.orchestrator import orchestrator
from app.api.models import OrchestratorInput

async def test_token_usage():
    print("\n--- Starting Routine Generation Token Test ---\n")
    
    # Mock Input
    test_input = OrchestratorInput(
        porosity="High",
        scalp="Oily",
        damage="High",
        density="Medium",
        texture="Curly"
    )
    
    start_time = time.time()
    token_summary = None
    
    try:
        async for chunk_str in orchestrator(test_input):
            chunk = json.loads(chunk_str)
            
            # Print status updates to show progress
            if chunk.get("type") == "status":
                print(f"Status: {chunk['content']}")
            
            # Capture the token log
            if chunk.get("type") == "token_summary":
                token_summary = chunk["content"]
                
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        
    end_time = time.time()
    duration = end_time - start_time
    
    print("\n" + "="*50)
    print("FINAL TOKEN USAGE REPORT")
    print("="*50)
    
    if token_summary:
        rg = token_summary.get("routine_generation", {})
        emb = token_summary.get("embeddings", {})
        
        print(f"\n[Routine Generation] ({rg.get('model')})")
        print(f"  Prompt Tokens:      {rg.get('prompt_tokens', 0):,}")
        print(f"  Completion Tokens:  {rg.get('completion_tokens', 0):,}")
        print(f"  Total Tokens:       {rg.get('total_tokens', 0):,}")
        
        print(f"\n[Embeddings] ({emb.get('model')})")
        print(f"  API Calls:          {emb.get('calls', 0)}")
        print(f"  Total Tokens:       {emb.get('total_tokens', 0):,}")
        
        print("-" * 30)
        print(f"GRAND TOTAL TOKENS:   {token_summary.get('grand_total_tokens', 0):,}")
        print(f"ESTIMATED COST:       ${token_summary.get('estimated_cost_usd', 0.0):.6f}")
        print("-" * 30)
    else:
        print("No token summary received.")
        
    print(f"\nTotal Time: {duration:.2f}s")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(test_token_usage())
