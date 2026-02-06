
import requests
import uuid

BASE_URL = "http://localhost:8000"

def test_large_prompt():
    user_id = "test_user"
    session_id = str(uuid.uuid4())
    
    # Simulating the user's long tech-architect prompt
    large_msg = """Role: You are the Lead AI Architect and Socratic Sparring Partner for a high-level Technical Founder. No fluff. Architecture breakthrough. Maintain a technical, candid, and intellectually rigorous tone. No code unless explicitly requested. Instead, pressure-test the user's architectural assumptions. Ask the one question that exposes a hidden complexity or flaw.
    
    Current focus: Scalable Vector Database design with hybrid search and real-time re-ranking. Give me your most critical assessment of using Pinecone with a custom caching layer for frequent user contexts."""
    
    print("Sending large prompt...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json={
                "user_id": user_id,
                "message": large_msg,
                "session_id": session_id
            },
            timeout=60
        )
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_large_prompt()
