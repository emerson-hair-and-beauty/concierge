
from google import genai
import os
from app.config import GEMINI_API_KEY
import asyncio

async def test_model():
    client = genai.Client(api_key=GEMINI_API_KEY)
    model_name = "gemini-2.5-flash-lite" # The one I used
    print(f"Testing model: {model_name}")
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents="test"
        )
        print("Success!")
    except Exception as e:
        print(f"Error for {model_name}: {e}")
        
    # Check what models are available
    print("\n--- Listing Models ---")
    try:
        # Check standard names
        for m in ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp"]:
             print(f"Checking {m}...")
             try:
                 await client.aio.models.generate_content(model=m, contents="hi")
                 print(f"  {m} is AVAILABLE")
             except Exception:
                 print(f"  {m} is unavailable")
    except Exception as e:
        print(f"List error: {e}")

if __name__ == "__main__":
    asyncio.run(test_model())
