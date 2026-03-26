import asyncio
import httpx
from datetime import datetime

async def test_api():
    base_url = "http://127.0.0.1:8001"
    
    print("\n--- 1. Testing /api/user/wash ---")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/api/user/wash",
                json={"user_id": "test-user-123"}
            )
            print(f"Status: {resp.status_code}")
            print(f"Reply:  {resp.json()}")
    except Exception as e:
        print(f"Failed to hit endpoint: {e}")

    print("\n--- 2. Testing /api/user/location ---")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/api/user/location",
                json={"user_id": "test-user-123", "location": "London, UK"}
            )
            print(f"Status: {resp.status_code}")
            print(f"Reply:  {resp.json()}")
    except Exception as e:
        print(f"Failed to hit endpoint: {e}")
        
    print("\n--- 3. Testing /api/scenarios/run ---")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base_url}/api/scenarios/run")
            print(f"Status: {resp.status_code}")
            print(f"Reply:  {resp.json()}")
    except Exception as e:
        print(f"Failed to hit endpoint: {e}")

    print("\n--- 4. Testing /api/user/alerts ---")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{base_url}/api/user/alerts",
                params={"user_id": "test-user-123"}
            )
            print(f"Status: {resp.status_code}")
            data = resp.json()
            print(f"Reply:  {data}")
            
            if data.get("alerts"):
                alert_id = data["alerts"][0]["id"]
                print(f"\n--- 5. Testing /api/user/alerts/{alert_id}/read ---")
                resp_read = await client.post(f"{base_url}/api/user/alerts/{alert_id}/read")
                print(f"Status: {resp_read.status_code}")
                print(f"Reply:  {resp_read.json()}")
    except Exception as e:
        print(f"Failed to hit endpoint: {e}")

if __name__ == "__main__":
    asyncio.run(test_api())
