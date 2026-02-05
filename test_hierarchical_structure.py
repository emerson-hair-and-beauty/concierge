"""
Test hierarchical structure: user_id → session_id → messages
"""

import requests
import uuid

BASE_URL = "http://localhost:8000"

def test_hierarchical_structure():
    print("=" * 70)
    print("TESTING HIERARCHICAL STRUCTURE: user_id → session_id → messages")
    print("=" * 70)
    
    # Create one user with two different sessions
    user_id = f"user-{str(uuid.uuid4())[:8]}"
    session_1 = f"session-1-{str(uuid.uuid4())[:8]}"
    session_2 = f"session-2-{str(uuid.uuid4())[:8]}"
    
    print(f"\n📋 Test Setup:")
    print(f"   User ID: {user_id}")
    print(f"   Session 1: {session_1}")
    print(f"   Session 2: {session_2}")
    print("=" * 70)
    
    # Session 1: Dry hair issue
    print(f"\n[Session 1] Message 1:")
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "user_id": user_id,
            "session_id": session_1,
            "message": "My hair feels dry"
        },
        timeout=30
    )
    print(f"   ✅ Status: {response.status_code}")
    
    # Session 2: Scalp issue (same user, different session)
    print(f"\n[Session 2] Message 1:")
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "user_id": user_id,
            "session_id": session_2,
            "message": "My scalp is itchy"
        },
        timeout=30
    )
    print(f"   ✅ Status: {response.status_code}")
    
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE!")
    print("=" * 70)
    print(f"\n📊 Verification in Supabase:")
    print(f"1. Go to Table Editor → chat_messages")
    print(f"2. Filter by user_id: {user_id}")
    print(f"3. You should see messages from BOTH sessions")
    print(f"4. Structure: {user_id}")
    print(f"   ├── {session_1} (dry hair)")
    print(f"   └── {session_2} (itchy scalp)")
    print("=" * 70)

if __name__ == "__main__":
    try:
        test_hierarchical_structure()
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
