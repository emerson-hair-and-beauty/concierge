import asyncio
import json
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.web_chat_agent.orchestrator import orchestrate_web_chat

async def test_session(user_id: str, messages: list):
    print(f"\n{'='*70}")
    print(f"STARTING STATEFUL SESSION FOR USER: {user_id}")
    print(f"{'='*70}")
    
    history = []
    session_id = f"session-{user_id}"
    
    for msg in messages:
        print(f"\n>>> USER: {msg}")
        
        full_assistant_msg = ""
        async for event in orchestrate_web_chat(history, msg, session_id=session_id, user_id=user_id):
            if event["type"] == "status":
                print(f"    [STATUS]: {event['content']}")
            elif event["type"] == "content":
                print(event["content"], end="", flush=True)
                full_assistant_msg += event["content"]
            elif event["type"] == "error":
                print(f"\n    [ERROR]: {event['content']}")
        
        print("\n" + "-" * 30)
        history.append({"role": "user", "message": msg})
        history.append({"role": "assistant", "message": full_assistant_msg})

async def main():
    # Scenario: A user who reveals their hair type gradually
    test_msgs = [
        "Hi! I have really thick, High Porosity curls and I'm looking for a routine.",
        "I'm also worried about the GCC humidity. What should I do?",
        "That's helpful. Also, what is your return policy and do you have a heavy mask for me?"
    ]
    
    await test_session("pro-curler-001", test_msgs)

if __name__ == "__main__":
    asyncio.run(main())
