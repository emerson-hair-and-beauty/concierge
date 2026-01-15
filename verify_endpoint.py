import httpx
import json
import asyncio

async def test_endpoint_stream():
    url = "https://concierge-jzf8.onrender.com/orchestrator/run-orchestrator"
    # url = "http://127.0.0.1:8000/orchestrator/run-orchestrator"
    payload = {
        "porosity": "High",
        "scalp": "Oily",
        "damage": "High",
        "density": "Medium",
        "texture": "Curly"
    }
    
    print(f"--- Calling Endpoint: {url} ---")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    print(f"Error: Status {response.status_code}")
                    print(await response.aread())
                    return
                
                async for line in response.aiter_lines():
                    if line:
                        print(f"RECVD: {line}")
    except Exception as e:
        print(f"ERROR calling endpoint: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_endpoint_stream())
