import asyncio
import json
from app.web_chat_agent.orchestrator import orchestrate_web_chat
from app.web_chat_agent.orchestrator_v2 import orchestrate_web_chat_v2

async def run_comparison(query):
    print(f"\n{'='*50}")
    print(f"QUERY: {query}")
    print(f"{'='*50}")

    # Run V1
    print("\n[V1 - TRIAGE SYSTEM]")
    async for event in orchestrate_web_chat([], query, session_id="comp-v1"):
        if event.get("type") == "content":
            print(event["content"], end="", flush=True)
    print("\n")

    # Run V2
    print("-" * 50)
    print("\n[V2 - DECOMPOSER SYSTEM]")
    async for event in orchestrate_web_chat_v2([], query, session_id="comp-v2"):
        if event.get("type") == "content":
            print(event["content"], end="", flush=True)
    print("\n")

async def main():
    queries = [
        "My curls are so dry, help!",
        "Build me a short routine for high porosity hair",
        "Where is my order?"
    ]
    
    for q in queries:
        await run_comparison(q)

if __name__ == "__main__":
    asyncio.run(main())
