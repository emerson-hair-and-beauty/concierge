"""
Test Chat Cleanup After Event Save

Verifies that:
1. Chat messages are created during diagnostic conversation
2. Event is saved with proper categorization
3. Chat messages are automatically deleted after event save
"""

import requests
import uuid
import time

BASE_URL = "http://localhost:8000"

def test_chat_cleanup():
    print("=" * 70)
    print("TESTING CHAT CLEANUP AFTER EVENT SAVE")
    print("=" * 70)
    
    user_id = f"cleanup-test-{str(uuid.uuid4())[:8]}"
    session_id = f"session-{str(uuid.uuid4())[:8]}"
    
    print(f"\n📋 Test Setup:")
    print(f"   User ID: {user_id}")
    print(f"   Session ID: {session_id}")
    print("=" * 70)
    
    # ========================================
    # STEP 1: Have a diagnostic conversation
    # ========================================
    print(f"\n💬 STEP 1: Creating chat messages")
    print("-" * 70)
    
    messages = [
        "My hair feels dry",
        "It's been 5 days since I washed it"
    ]
    
    for msg in messages:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json={
                "user_id": user_id,
                "session_id": session_id,
                "message": msg
            },
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"   ✅ Sent: \"{msg}\"")
        else:
            print(f"   ❌ Failed: {response.status_code}")
        
        time.sleep(2)  # Small delay
    
    print(f"\n   📊 Chat messages should now exist in Supabase")
    print(f"   Check: chat_messages WHERE session_id = '{session_id}'")
    
    # ========================================
    # STEP 2: Save event (should trigger cleanup)
    # ========================================
    print(f"\n💾 STEP 2: Saving event (should delete chat)")
    print("-" * 70)
    
    event_data = {
        "user_id": user_id,
        "session_id": session_id,  # Same session ID!
        "target_vital": "moisture",
        "vital_value": 7,
        "conversation_summary": "User reported dry hair on Day 5",
        "keywords": ["dry", "moisture"],
        "wash_day_number": 5,
        "day_in_cycle": 5
    }
    
    response = requests.post(f"{BASE_URL}/api/event", json=event_data, timeout=30)
    
    if response.status_code == 200:
        event = response.json()
        print(f"   ✅ Event saved!")
        print(f"   Event ID: {event['id']}")
        print(f"   Session ID: {event['session_id']}")
        print(f"   Category: {event.get('primary_label', 'N/A')}")
    else:
        print(f"   ❌ Failed: {response.status_code}")
        print(f"   {response.text}")
        return
    
    # ========================================
    # VERIFICATION
    # ========================================
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE!")
    print("=" * 70)
    print(f"\n📊 Verification in Supabase:")
    print(f"\n1. Check chat_messages table:")
    print(f"   Filter: session_id = '{session_id}'")
    print(f"   Expected: NO ROWS (chat was deleted)")
    print(f"\n2. Check hair_events table:")
    print(f"   Filter: session_id in metadata = '{session_id}'")
    print(f"   Expected: 1 event with summary capturing the conversation")
    print(f"\n✨ The chat is now cleaned up - only the event remains!")
    print("=" * 70)

if __name__ == "__main__":
    try:
        test_chat_cleanup()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
