import asyncio
import httpx
import json

async def test_onboarding_orchestrator():
    base_url = "http://127.0.0.1:8001"
    
    payload = {
        "user_id": "integration-test-user-123",
        "first_name": "Test",
        "email": "test@example.com",
        "location": "Dubai, UAE",
        "gender": "Female",
        "hair_length": "Shoulder to Mid Back",
        "texture": "Spring curls",
        "density": "Medium",
        "moisture_behaviour": "Low Porosity",
        "humidity_response": "Expand and become frizzy",
        "hair_goals": ["Long-lasting definition", "Frizz control", "Moisture retention"]
    }
    
    print("\n--- Testing /orchestrator/run-orchestrator ---")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{base_url}/orchestrator/run-orchestrator", json=payload) as response:
                print(f"Status: {response.status_code}")
                if response.status_code != 200:
                    body = await response.aread()
                    print(f"Error Response: {body.decode()}")
                    return
                
                print("\nStreaming response:")
                async for chunk in response.aiter_lines():
                    if chunk:
                        try:
                            data = json.loads(chunk)
                            if data.get("type") == "status":
                                print(f"[STATUS] {data.get('content')}")
                            elif data.get("type") == "product_recommendation":
                                step = data.get("content", {}).get("step")
                                action = data.get("content", {}).get("action")
                                print(f"[STEP] {step}: {action}")
                            elif data.get("type") == "token_summary":
                                print(f"\n[COMPLETE] Cost: ${data.get('content', {}).get('estimated_cost_usd'):.5f}")
                            else:
                                print(f"[OTHER] {chunk[:100]}...")
                        except json.JSONDecodeError:
                            # Not JSON, might be raw text if orchestrator fails
                            print(f"[RAW] {chunk}")
                            
    except Exception as e:
        print(f"Failed to hit endpoint: {e}")

if __name__ == "__main__":
    asyncio.run(test_onboarding_orchestrator())
