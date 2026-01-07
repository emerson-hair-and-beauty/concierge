import asyncio
import sys
import os

# Add the project root to sys.path so we can import 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.agents.orchestrator import orchestrator
from app.api.models import OrchestratorInput

import time

async def test_streaming():
    test_input = OrchestratorInput(
        porosity="High",
        scalp="Oily",
        damage="High",
        density="Medium",
        texture="Curly"
    )
    
    print("--- Starting Orchestrator Stream ---", flush=True)
    start_time = time.time()
    try:
        async for chunk_str in orchestrator(test_input):
            print(f"RECVD: {chunk_str.strip()}", flush=True)
    except Exception as e:
        print(f"ERROR: {str(e)}", flush=True)
    end_time = time.time()
    print(f"--- Stream Finished (Total time: {end_time - start_time:.2f}s) ---", flush=True)

if __name__ == "__main__":
    asyncio.run(test_streaming())
