"""
Test script for Empath Diagnostic Engine Vertical Slice
Simulates the complete user journey from chat to event save
"""

import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000"

async def test_vertical_slice():
    """Test the complete diagnostic flow"""
    
    print("=" * 60)
    print("EMPATH DIAGNOSTIC ENGINE - VERTICAL SLICE TEST")
    print("=" * 60)
    
    user_id = "test_user_123"
    session_id = "test_session_456"
    
    async with httpx.AsyncClient() as client:
        
        # Step 1: User's initial complaint
        print("\n[1] User: 'My hair feels like straw'")
        response = await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "user_id": user_id,
                "message": "My hair feels like straw",
                "session_id": session_id
            }
        )
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            return

        data = response.json()
        print(f"Assistant: {data['message']}")
        print(f"Handoff: {data['handoff']}")
        
        # Step 2: User clarifies
        print("\n[2] User: 'Snapping when I brush it'")
        response = await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "user_id": user_id,
                "message": "Snapping when I brush it",
                "session_id": session_id
            }
        )
        data = response.json()
        print(f"Assistant: {data['message']}")
        print(f"Handoff: {data['handoff']}")
        
        # Step 3: User provides wash day info
        print("\n[3] User: 'Day 5'")
        response = await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "user_id": user_id,
                "message": "Day 5",
                "session_id": session_id
            }
        )
        data = response.json()
        print(f"Assistant: {data['message']}")
        print(f"Handoff: {data['handoff']}")
        print(f"Target Vital: {data.get('target_vital')}")
        
        # If handoff detected, save the event
        if data['handoff']:
            print("\n" + "=" * 60)
            print("CHECKPOINT DETECTED - Saving Event")
            print("=" * 60)
            
            print(f"Backend Summary: {data.get('summary')}")
            print(f"Backend Keywords: {', '.join(data.get('keywords', []))}")
            
            # Step 4: User provides slider value
            slider_value = 7  # User rates breakage as 7/10
            print(f"\n[4] User sets {data['target_vital']} slider to: {slider_value}/10")
            
            event_response = await client.post(
                f"{BASE_URL}/api/event",
                json={
                    "user_id": user_id,
                    "session_id": session_id,
                    "target_vital": data['target_vital'],
                    "vital_value": slider_value,
                    "conversation_summary": data.get('summary'), # Use backend summary
                    "keywords": data.get('keywords'),           # Use backend keywords
                    "wash_day_number": 5,
                    "day_in_cycle": 5
                }
            )
            event_data = event_response.json()
            print(f"\n✅ Event Saved!")
            print(f"Event ID: {event_data['id']}")
            print(f"Created: {event_data['created_at']}")
            print(f"Vitals: {json.dumps(event_data['vitals_payload'], indent=2)}")
            
            # Step 5: Retrieve user's events
            print("\n" + "=" * 60)
            print("RETRIEVING USER EVENTS")
            print("=" * 60)
            
            events_response = await client.get(f"{BASE_URL}/api/events/{user_id}")
            events_data = events_response.json()
            print(f"\nTotal events for {user_id}: {events_data['count']}")
            for i, event in enumerate(events_data['events'], 1):
                print(f"\nEvent {i}:")
                print(f"  ID: {event['id']}")
                print(f"  Summary: {event['conversation_summary']}")
                print(f"  Keywords: {', '.join(event['keywords'])}")
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_vertical_slice())
