from google import genai
import os
import sys

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
from app.config import GEMINI_API_KEY

def test_minimal():
    print(f"Testing with API Key: {GEMINI_API_KEY[:5]}...", flush=True)
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents="Hello, say 'Test successful' if you receive this."
        )
        print(f"RESPONSE: {response.text}", flush=True)
    except Exception as e:
        print(f"ERROR: {str(e)}", flush=True)

if __name__ == "__main__":
    test_minimal()
