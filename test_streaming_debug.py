
import asyncio
import os
import sys
from google import genai

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
from app.config import GEMINI_API_KEY

async def test_streaming():
    print("Testing generate_content_stream with gemini-2.5-flash-lite...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = "Hello, say 'Stream works' if you receive this."
    model = "gemini-2.5-flash-lite"
    
    try:
        # Configuration setup similar to llm_call.py
        config = {}
        if "thinking" in model:
             config["thinking_config"] = {"include_thoughts": True, "thinking_budget": 1024}
             
        response = await client.aio.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=config
        )
        
        print("Stream started...")
        full_text = ""
        async for chunk in response:
            print(f"Chunk received: {chunk.text}")
            if chunk.text:
                full_text += chunk.text
                
        print(f"FULL RESPONSE: {full_text}")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_streaming())
