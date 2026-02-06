
from google import genai
import os
from app.config import GEMINI_API_KEY
import asyncio

async def list_models():
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("--- AVAILABLE MODELS ---")
    try:
        # Note: list_models is often synchronous or different in SDK versions
        # Looking at documentation for google-genai
        for model in client.models.list():
            if "generateContent" in model.supported_generation_methods:
                print(f"Model ID: {model.name}")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    asyncio.run(list_models())
