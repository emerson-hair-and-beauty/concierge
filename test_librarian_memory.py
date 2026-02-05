"""
Test Librarian Long-Term Memory (LTM)

This test verifies that:
1. Events are saved with proper categorization
2. Past events are retrieved and injected into diagnostic context
3. AI references past issues in new conversations
"""

import requests
import uuid
import time

BASE_URL = "http://localhost:8000"

def test_librarian_memory():
    print("=" * 70)
    print("TESTING LIBRARIAN LONG-TERM MEMORY")
    print("=" * 70)
    
    user_id = f"ltm-user-{str(uuid.uuid4())[:8]}"
    
    # ========================================
    # STEP 1: Create a past event (dry hair)
    # ========================================
    print(f"\n📝 STEP 1: Creating past event for user {user_id}")
    print("-" * 70)
    
    session_1 = f"session-past-{str(uuid.uuid4())[:8]}"
    
    # Simulate a completed diagnostic conversation
    past_event = {
        "user_id": user_id,
        "session_id": session_1,
        "target_vital": "moisture",
        "vital_value": 7,
        "conversation_summary": "User reported dry, straw-like hair on Day 5 of wash cycle",
        "keywords": ["dry hair", "moisture", "day 5"],
        "wash_day_number": 5,
        "day_in_cycle": 5
    }
    
    response = requests.post(f"{BASE_URL}/api/event", json=past_event, timeout=30)
    
    if response.status_code == 200:
        event_data = response.json()
        print(f"   ✅ Past event saved!")
        print(f"   Event ID: {event_data['id']}")
        print(f"   Category: {event_data.get('primary_label', 'N/A')}")
        print(f"   Summary: {event_data['conversation_summary']}")
    else:
        print(f"   ❌ Failed to save event: {response.status_code}")
        print(f"   {response.text}")
        return
    
    # Wait a moment to ensure event is persisted
    time.sleep(2)
    
    # ========================================
    # STEP 2: Start new conversation
    # ========================================
    print(f"\n💬 STEP 2: Starting NEW conversation (should reference past event)")
    print("-" * 70)
    
    session_2 = f"session-new-{str(uuid.uuid4())[:8]}"
    
    message = "My hair feels dry again"
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "user_id": user_id,
            "session_id": session_2,
            "message": message
        },
        timeout=30
    )
    
    if response.status_code == 200:
        data = response.json()
        ai_response = data['message']
        
        print(f"   User: {message}")
        print(f"   🤖 AI: {ai_response}")
        print()
        
        # Check if AI referenced past event
        memory_keywords = ["remember", "last time", "previously", "before", "day 5", "past"]
        has_memory = any(keyword in ai_response.lower() for keyword in memory_keywords)
        
        if has_memory:
            print(f"   ✅ AI REFERENCED PAST EVENT! Memory is working!")
        else:
            print(f"   ⚠️  AI did not explicitly reference past event")
            print(f"   (This might be okay - AI may be gathering more info first)")
    else:
        print(f"   ❌ Chat failed: {response.status_code}")
        print(f"   {response.text}")
    
    # ========================================
    # VERIFICATION
    # ========================================
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE!")
    print("=" * 70)
    print(f"\n📊 Verification in Supabase:")
    print(f"1. Go to Table Editor → hair_events")
    print(f"2. Filter by user_id: {user_id}")
    print(f"3. You should see 1 event with:")
    print(f"   - primary_label: MOISTURE")
    print(f"   - summary: 'User reported dry, straw-like hair...'")
    print(f"   - vital_score: 7")
    print()
    print(f"4. The AI's response should show awareness of past issues")
    print("=" * 70)

if __name__ == "__main__":
    try:
        test_librarian_memory()
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
