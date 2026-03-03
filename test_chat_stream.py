"""
SSE streaming chat test — prints each delta as it arrives with timestamps.
Usage: python test_chat_stream.py [BASE_URL]
"""

import httpx
import time
import sys
import uuid
import json

BASE_URL   = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
USER_ID    = f"stream_test_{uuid.uuid4().hex[:8]}"
SESSION_ID = f"session_{uuid.uuid4().hex[:8]}"

MESSAGES = [
    "My hair feels really dry and brittle lately.",
    "I wash it twice a week and use a leave-in conditioner.",
    "It started getting worse about a month ago after I bleached it.",
]

def ts():
    return time.strftime("%H:%M:%S")

def run_turn(client, message, turn):
    print(f"\n[{ts()}] Turn {turn}: \"{message}\"")
    t_start = time.perf_counter()
    t_first_chunk = None

    with client.stream(
        "POST",
        f"{BASE_URL}/api/chat/stream",
        json={"user_id": USER_ID, "message": message, "session_id": SESSION_ID},
        timeout=90.0,
    ) as response:
        if response.status_code != 200:
            print(f"  ❌ HTTP {response.status_code}")
            print(response.text[:300])
            return

        print("  Streaming: ", end="", flush=True)
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[len("data: "):]
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if event["type"] == "delta":
                if t_first_chunk is None:
                    t_first_chunk = time.perf_counter()
                print(event["content"], end="", flush=True)

            elif event["type"] == "done":
                total = time.perf_counter() - t_start
                ttfc  = (t_first_chunk - t_start) if t_first_chunk else None
                print()  # newline after streamed text
                print(f"  ✅ Total: {total:.2f}s | Time-to-first-chunk: {ttfc:.2f}s" if ttfc else f"  ✅ Total: {total:.2f}s")
                print(f"     handoff={event['handoff']} | target_vital={event.get('target_vital')}")

            elif event["type"] == "error":
                print(f"\n  ❌ Error: {event['detail']}")

if __name__ == "__main__":
    print("=" * 60)
    print(f"TARGET:     {BASE_URL}/api/chat/stream")
    print(f"USER_ID:    {USER_ID}")
    print(f"SESSION_ID: {SESSION_ID}")
    print("=" * 60)

    with httpx.Client() as client:
        for i, msg in enumerate(MESSAGES, 1):
            run_turn(client, msg, i)
