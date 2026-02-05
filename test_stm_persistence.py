"""
Test Script: Short-Term Memory (STM) Persistence
Tests that chat history persists across server restarts
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_stm_persistence():
    print("=" * 60)
    print("Testing Short-Term Memory (STM) Persistence")
    print("=" * 60)
    
    # Test session
    session_id = "test-session-stm-001"
    user_id = "test-user-123"
    
    print(f"\n1️⃣ Sending first message...")
    response1 = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "user_id": user_id,
            "session_id": session_id,
            "message": "My hair feels really dry and brittle"
        }
    )
    
    if response1.status_code == 200:
        data1 = response1.json()
        print(f"✅ Response: {data1['message'][:100]}...")
        print(f"   Handoff: {data1['handoff']}")
    else:
        print(f"❌ Error: {response1.status_code} - {response1.text}")
        return
    
    print(f"\n2️⃣ Sending second message...")
    response2 = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "user_id": user_id,
            "session_id": session_id,
            "message": "It's day 3 after my wash day"
        }
    )
    
    if response2.status_code == 200:
        data2 = response2.json()
        print(f"✅ Response: {data2['message'][:100]}...")
        print(f"   Handoff: {data2['handoff']}")
    else:
        print(f"❌ Error: {response2.status_code} - {response2.text}")
        return
    
    print(f"\n3️⃣ Sending third message (should have context from previous 2)...")
    response3 = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "user_id": user_id,
            "session_id": session_id,
            "message": "Yes, that sounds right"
        }
    )
    
    if response3.status_code == 200:
        data3 = response3.json()
        print(f"✅ Response: {data3['message'][:150]}...")
        print(f"   Handoff: {data3['handoff']}")
        if data3['handoff']:
            print(f"   Target Vital: {data3['target_vital']}")
            print(f"   Summary: {data3.get('summary', 'N/A')[:100]}...")
    else:
        print(f"❌ Error: {response3.status_code} - {response3.text}")
        return
    
    print("\n" + "=" * 60)
    print("✅ STM Test Complete!")
    print("=" * 60)
    print("\n📋 Next Steps:")
    print("1. Check your Supabase dashboard → chat_messages table")
    print("2. You should see 6 rows (3 user + 3 assistant messages)")
    print("3. Restart the server with Ctrl+C and run this script again")
    print("4. The AI should remember the conversation context")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_stm_persistence()
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to server at http://localhost:8000")
        print("   Make sure the server is running: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
