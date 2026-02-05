"""
Simple debug script to see the exact 500 error
"""

import requests
import json

BASE_URL = "http://localhost:8000"

print("Testing /api/chat endpoint...")
print("=" * 60)

try:
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "user_id": "debug-user",
            "session_id": "debug-session",
            "message": "Hello"
        },
        timeout=30
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print(f"\nResponse Body:")
    print(response.text)
    
    if response.status_code == 200:
        print("\n✅ Success!")
        data = response.json()
        print(f"Message: {data.get('message')}")
    else:
        print(f"\n❌ Error {response.status_code}")
        try:
            error_data = response.json()
            print(f"Error Detail: {json.dumps(error_data, indent=2)}")
        except:
            print(f"Raw Error: {response.text}")
            
except requests.exceptions.ConnectionError:
    print("❌ Cannot connect to server. Is it running on http://localhost:8000?")
except Exception as e:
    print(f"❌ Unexpected error: {str(e)}")
    import traceback
    traceback.print_exc()
