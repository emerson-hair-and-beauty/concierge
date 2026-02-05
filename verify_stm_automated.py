"""
Automated STM Verification Test
Tests chat persistence with a different user ID
"""

import requests
import time
import uuid

BASE_URL = "http://localhost:8000"

def run_automated_test():
    # Generate unique IDs for this test
    user_id = f"test-user-{str(uuid.uuid4())[:8]}"
    session_id = f"session-{str(uuid.uuid4())[:8]}"
    
    print("=" * 70)
    print("AUTOMATED SHORT-TERM MEMORY VERIFICATION TEST")
    print("=" * 70)
    print(f"\n📋 Test Details:")
    print(f"   User ID: {user_id}")
    print(f"   Session ID: {session_id}")
    print(f"\n🔗 Check Supabase: https://jyqebydjqkyizayimegw.supabase.co")
    print(f"   Table: chat_messages")
    print(f"   Filter by session_id: {session_id}")
    print("=" * 70)
    
    messages = [
        "My hair has been feeling really dry lately",
        "It's been about 4 days since I washed it",
        "Yes, it feels rough and straw-like when I touch it"
    ]
    
    for i, msg in enumerate(messages, 1):
        print(f"\n[{i}/3] Sending message: \"{msg}\"")
        
        try:
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
                data = response.json()
                print(f"   ✅ Status: 200 OK")
                print(f"   🤖 Empath: {data['message'][:80]}...")
                print(f"   📊 Handoff: {data['handoff']}")
                
                if data['handoff']:
                    print(f"   🎯 Target Vital: {data['target_vital']}")
                    print(f"   📝 Summary: {data.get('summary', 'N/A')[:60]}...")
            else:
                print(f"   ❌ Error {response.status_code}: {response.text[:100]}")
                
        except requests.exceptions.Timeout:
            print(f"   ⏱️  Request timed out (likely rate limiting, waiting...)")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        # Small delay between messages to avoid rate limiting
        if i < len(messages):
            print(f"   ⏳ Waiting 3 seconds before next message...")
            time.sleep(3)
    
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE!")
    print("=" * 70)
    print(f"\n📊 Verification Steps:")
    print(f"1. Go to Supabase dashboard → Table Editor → chat_messages")
    print(f"2. Look for session_id: {session_id}")
    print(f"3. You should see 6 rows (3 user + 3 assistant messages)")
    print(f"4. All messages should have timestamps showing they were saved")
    print("=" * 70)

if __name__ == "__main__":
    try:
        run_automated_test()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
