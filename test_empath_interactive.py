"""
Interactive Test for Empath Diagnostic Engine
Chat with the Empath Agent in the terminal to verify the flow naturally.
"""

import asyncio
import httpx
import json
import sys
import uuid

BASE_URL = "http://localhost:8000"

async def interactive_session():
    print("=" * 60)
    print("EMPATH DIAGNOSTIC ENGINE - INTERACTIVE CLI")
    print("Type 'quit' or 'exit' to stop.")
    print("=" * 60)
    
    # Generate a fresh session for this test
    user_id = f"cli_user_{str(uuid.uuid4())[:8]}"
    session_id = f"cli_session_{str(uuid.uuid4())[:8]}"
    print(f"Session ID: {session_id}")
    print("-" * 60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        while True:
            # 1. Get User Input
            try:
                user_msg = input("\nYou: ").strip()
            except EOFError:
                break
                
            if user_msg.lower() in ['quit', 'exit']:
                break
            
            if not user_msg:
                continue
                
            # 2. Add visual indicator that we are waiting
            print("Empath is thinking...", end="\r", flush=True)

            try:
                # 3. Call Chat API
                response = await client.post(
                    f"{BASE_URL}/api/chat",
                    json={
                        "user_id": user_id,
                        "message": user_msg,
                        "session_id": session_id
                    }
                )
                
                if response.status_code != 200:
                    print(f"\nError {response.status_code}: {response.text}")
                    continue
                    
                data = response.json()
                
                # 4. Display Assistant Response
                # Clear 'thinking' line
                print(" " * 30, end="\r") 
                print(f"Empath: {data['message']}")
                
                # 5. Check for Handoff
                if data.get("handoff"):
                    target_vital = data.get("target_vital")
                    print(f"\n[!] HANDOFF TRIGGERED for: {target_vital.upper()}")
                    
                    # 6. Simulate UI Slider
                    while True:
                        try:
                            val_str = input(f"Rate your {target_vital} (1-10): ")
                            val = int(val_str)
                            if 1 <= val <= 10:
                                break
                            print("Please enter a number between 1 and 10.")
                        except ValueError:
                            print("Invalid input.")
                    
                    # 7. Save Event
                    print("Saving event...", end="\r")
                    event_response = await client.post(
                        f"{BASE_URL}/api/event",
                        json={
                            "user_id": user_id,
                            "session_id": session_id,
                            "target_vital": target_vital,
                            "vital_value": val,
                            "conversation_summary": f"Diagnosed {target_vital} issue via CLI",
                            "keywords": ["cli_test"],
                            # Mock wash day info since we don't parse it from chat in this basic script
                            "wash_day_number": 1, 
                            "day_in_cycle": 1
                        }
                    )
                    
                    if event_response.status_code == 200:
                        evt = event_response.json()
                        print(f"\n✅ Event Saved Successfully!")
                        print(f"ID: {evt['id']}")
                        print(f"Vitals: {evt['vitals_payload']}")
                    else:
                        print(f"\n❌ Failed to save event: {event_response.text}")
                        
                    print("\nDiagnostic complete. Starting new session? (y/n)")
                    if input().lower() != 'y':
                        break
                    else:
                        # Reset for new session
                        session_id = f"cli_session_{str(uuid.uuid4())[:8]}"
                        print(f"\nNew Session ID: {session_id}")
                        print("-" * 60)

            except Exception as e:
                print(f"\nRequest failed: {str(e)}")

if __name__ == "__main__":
    try:
        asyncio.run(interactive_session())
    except KeyboardInterrupt:
        print("\n\nExiting...")
