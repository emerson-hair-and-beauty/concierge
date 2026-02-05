
import requests
import uuid
import json

BASE_URL = "http://localhost:8000"

def debug_chat_endpoint():
    print("=" * 70)
    print("DEBUGGING CHAT ENDPOINT (500 ERROR)")
    print("=" * 70)
    
    user_id = f"debug-chat-{str(uuid.uuid4())[:8]}"
    session_id = f"debug-sess-{str(uuid.uuid4())[:8]}"
    
    print(f"User: {user_id}")
    print(f"Session: {session_id}")
    
    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "message": "My hair feels dry"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/chat", json=payload, timeout=30)
        
        print(f"\nStatus Code: {response.status_code}")
        if response.status_code == 200:
            print("Response:", response.json())
        else:
            print("Response Text:", response.text)
            
    except Exception as e:
        print(f"\nRequests Error: {e}")

if __name__ == "__main__":
    debug_chat_endpoint()
