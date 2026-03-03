"""
Live chat latency test — fires at the Render endpoint and logs per-step timing.
Usage: python test_chat_latency.py [BASE_URL]
  e.g. python test_chat_latency.py https://concierge-jzf8.onrender.com
"""

import asyncio
import httpx
import time
import sys
import uuid

BASE_URL   = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
USER_ID    = f"latency_test_{uuid.uuid4().hex[:8]}"
SESSION_ID = f"session_{uuid.uuid4().hex[:8]}"

MESSAGES = [
    "My hair feels really dry and brittle lately.",
    "I wash it twice a week and use a leave-in conditioner.",
    "It started getting worse about a month ago after I bleached it.",
]

def ts():
    return time.strftime("%H:%M:%S")

async def main():
    print("=" * 60)
    print(f"TARGET:     {BASE_URL}")
    print(f"USER_ID:    {USER_ID}")
    print(f"SESSION_ID: {SESSION_ID}")
    print("=" * 60)

    # Health check
    async with httpx.AsyncClient() as client:
        t0 = time.perf_counter()
        try:
            r = await client.get(f"{BASE_URL}/health", timeout=15.0)
            print(f"[{ts()}] /health → {r.status_code} in {time.perf_counter()-t0:.2f}s")
        except Exception as e:
            print(f"[{ts()}] /health → FAILED: {e}")

        timings = []
        for i, msg in enumerate(MESSAGES, 1):
            print(f"\n[{ts()}] Turn {i}: \"{msg}\"")
            t0 = time.perf_counter()
            try:
                r = await client.post(
                    f"{BASE_URL}/api/chat",
                    json={"user_id": USER_ID, "message": msg, "session_id": SESSION_ID},
                    timeout=90.0,
                )
                elapsed = time.perf_counter() - t0
                data = r.json()
                handoff = data.get("handoff")
                reply   = data.get("message", "")[:100]
                print(f"  -> {elapsed:.2f}s | HTTP {r.status_code} | handoff={handoff}")
                print(f"     reply: {reply}")
                timings.append(elapsed)
            except httpx.TimeoutException:
                elapsed = time.perf_counter() - t0
                print(f"  -> TIMEOUT after {elapsed:.2f}s")
            except Exception as e:
                elapsed = time.perf_counter() - t0
                print(f"  -> ERROR after {elapsed:.2f}s: {e}")

            await asyncio.sleep(0.3)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if timings:
        print(f"  Turns completed : {len(timings)}/{len(MESSAGES)}")
        print(f"  Fastest         : {min(timings):.2f}s")
        print(f"  Slowest         : {max(timings):.2f}s")
        print(f"  Average         : {sum(timings)/len(timings):.2f}s")
        print(f"  Total           : {sum(timings):.2f}s")
    else:
        print("  No successful turns.")

if __name__ == "__main__":
    asyncio.run(main())
