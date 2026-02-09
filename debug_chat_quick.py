"""
Quick debug script to test chat endpoint and see full error
"""
import asyncio
import httpx
import json

async def test_chat():
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "http://localhost:8000/api/chat",
                json={
                    "user_id": "debug_user",
                    "session_id": "debug_session",
                    "message": "My hair has been breaking"
                }
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            
        except Exception as e:
            print(f"Error: {e}")
            if hasattr(e, 'response'):
                print(f"Response text: {e.response.text}")

if __name__ == "__main__":
    asyncio.run(test_chat())
