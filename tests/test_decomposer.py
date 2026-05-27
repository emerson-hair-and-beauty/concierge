import asyncio
import json
from app.web_chat_agent.decomposer import Decomposer

async def test_decomposer():
    decomposer = Decomposer()
    
    scenarios = [
        "My hair is always dry no matter what I use",
        "Difference between gel and mousse?",
        "What products do you have for curls?",
        "Build me a routine for low porosity hair",
        "How's my order doing?"
    ]
    
    print("--- DECOMPOSER TEST ---\n")
    
    for query in scenarios:
        print(f"QUERY: {query}")
        decision = await decomposer.decompose(query)
        print(f"DECISION: {json.dumps(decision, indent=2)}\n")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_decomposer())
