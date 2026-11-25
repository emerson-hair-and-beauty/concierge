"""Load test for the three chat endpoints.

The test opens N users at the same time on each chat. Each user sends a short
conversation, one message after the other. The test records the time for
each reply and fails loudly when a reply is slow, empty, or an error.

Usage:
    python scripts/load_test_chats.py
    python scripts/load_test_chats.py --base-url http://127.0.0.1:8000 --users 5
    python scripts/load_test_chats.py --chats advisor --users 10

Pass criteria for each reply:
    - HTTP status 200
    - no "error" event in the stream
    - reply text that is not empty
    - stream ends with a "done" event (empath stream and web chat only)
    - total reply time less than --max-seconds

The script exits with code 1 if one reply fails. It writes a JSON report with
all the results next to this file.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://concierge-jzf8.onrender.com"

# The user IDs start with this prefix, so that you can find and delete the
# test data in the database.
USER_PREFIX = "loadtest"

CONVERSATIONS = {
    # The empath client sends an empty message first to get the greeting.
    "empath": [
        "",
        "My hair feels really dry and frizzy lately.",
        "It gets worse after I wash it, especially at the ends.",
    ],
    "advisor": [
        "What should I use for dry ends?",
        "I have curly hair, does that change anything?",
        "Do you have something that is not too heavy?",
    ],
    "web": [
        "Hi, what products do you have for frizz?",
        "My hair is curly and low porosity.",
        "Which one should I start with?",
    ],
}


@dataclass
class Result:
    chat: str
    user: int
    turn: int
    message: str
    ok: bool = False
    status: int | None = None
    seconds: float = 0.0
    first_content_seconds: float | None = None
    reply_chars: int = 0
    reply_preview: str = ""
    failures: list = field(default_factory=list)
    # Set when the advisor asks a clarification question. The next turn
    # sends this option label in place of the script message.
    next_message: str | None = None


def check_time(result, max_seconds):
    if result.seconds >= max_seconds:
        result.failures.append(f"slow reply: {result.seconds:.1f}s >= {max_seconds}s")


async def call_empath(client, base, user_id, session_id, message, result):
    """POST /api/chat. The reply is one JSON object."""
    resp = await client.post(
        f"{base}/api/chat",
        json={"user_id": user_id, "session_id": session_id, "message": message},
    )
    result.status = resp.status_code
    if resp.status_code != 200:
        result.failures.append(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return ""
    try:
        data = resp.json()
    except ValueError:
        result.failures.append(f"reply is not JSON: {resp.text[:300]}")
        return ""
    return data.get("message") or ""


async def call_advisor(client, base, user_id, session_id, message, result, t0):
    """POST /api/advisor/chat/stream. The reply is newline-delimited JSON."""
    text = ""
    body = {"user_id": user_id, "session_id": session_id, "message": message}
    async with client.stream("POST", f"{base}/api/advisor/chat/stream", json=body) as resp:
        result.status = resp.status_code
        if resp.status_code != 200:
            raw = await resp.aread()
            result.failures.append(f"HTTP {resp.status_code}: {raw[:300]!r}")
            return ""
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                result.failures.append(f"line is not JSON: {line[:200]}")
                continue
            kind = event.get("type")
            if kind == "error":
                result.failures.append(f"error event: {event.get('content')}")
            elif kind == "clarification":
                # A clarification question is a valid reply. The UI shows
                # the options as buttons, so the user answers with one label.
                content = event.get("content") or {}
                if result.first_content_seconds is None:
                    result.first_content_seconds = time.perf_counter() - t0
                text += f"[clarification] {content.get('question', '')}"
                options = content.get("options") or []
                if options:
                    result.next_message = options[0].get("label")
            elif kind == "content" and event.get("content"):
                if result.first_content_seconds is None:
                    result.first_content_seconds = time.perf_counter() - t0
                text += event["content"]
    return text


async def call_web(client, base, user_id, session_id, message, result, t0):
    """POST /api/web/chat/stream. The reply is server-sent events."""
    text = ""
    got_done = False
    body = {"user_id": user_id, "session_id": session_id, "message": message}
    async with client.stream("POST", f"{base}/api/web/chat/stream", json=body) as resp:
        result.status = resp.status_code
        if resp.status_code != 200:
            raw = await resp.aread()
            result.failures.append(f"HTTP {resp.status_code}: {raw[:300]!r}")
            return ""
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except ValueError:
                result.failures.append(f"event is not JSON: {line[:200]}")
                continue
            kind = event.get("type")
            if kind == "error":
                result.failures.append(f"error event: {event.get('detail') or event.get('content')}")
            elif kind == "done":
                got_done = True
            elif kind == "content" and event.get("content"):
                if result.first_content_seconds is None:
                    result.first_content_seconds = time.perf_counter() - t0
                text += event["content"]
    if not got_done and not result.failures:
        result.failures.append("stream ended without a 'done' event")
    return text


async def run_user(client, base, chat, user, max_seconds, run_id):
    user_id = f"{USER_PREFIX}-{run_id}-{chat}-{user}"
    session_id = str(uuid.uuid4())
    results = []
    for turn, message in enumerate(CONVERSATIONS[chat]):
        if results and results[-1].next_message:
            message = results[-1].next_message
        result = Result(chat=chat, user=user, turn=turn, message=message)
        t0 = time.perf_counter()
        try:
            if chat == "empath":
                text = await call_empath(client, base, user_id, session_id, message, result)
            elif chat == "advisor":
                text = await call_advisor(client, base, user_id, session_id, message, result, t0)
            else:
                text = await call_web(client, base, user_id, session_id, message, result, t0)
        except httpx.TimeoutException as e:
            text = ""
            result.failures.append(f"timeout: {type(e).__name__}")
        except httpx.HTTPError as e:
            text = ""
            result.failures.append(f"connection error: {type(e).__name__}: {e}")
        result.seconds = time.perf_counter() - t0
        if result.status == 200 and not text.strip() and not result.failures:
            result.failures.append("empty reply")
        check_time(result, max_seconds)
        result.reply_chars = len(text)
        result.reply_preview = text[:120].replace("\n", " ")
        result.ok = not result.failures
        results.append(result)

        mark = "PASS" if result.ok else "FAIL"
        line = f"  [{mark}] {chat:<7} user {user} turn {turn}  {result.seconds:5.1f}s"
        if result.first_content_seconds is not None:
            line += f"  (first text {result.first_content_seconds:4.1f}s)"
        if not result.ok:
            line += "  <-- " + "; ".join(result.failures)
        print(line, flush=True)
    return results


async def wake_server(client, base):
    """Render puts the free server to sleep. Wake it before the test."""
    print(f"Waking {base} ...", flush=True)
    t0 = time.perf_counter()
    for _ in range(12):
        try:
            resp = await client.get(f"{base}/health", timeout=30)
            if resp.status_code == 200:
                print(f"Server is up after {time.perf_counter() - t0:.1f}s.\n", flush=True)
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(5)
    print("SERVER DID NOT WAKE UP. The test stops.", flush=True)
    return False


def summarize(results, max_seconds):
    print("\n" + "=" * 72)
    print(f"SUMMARY  (target: every reply < {max_seconds}s, no errors)")
    print("=" * 72)
    print(f"{'chat':<8}{'replies':>8}{'fails':>7}{'p50':>8}{'p95':>8}{'max':>8}{'first text p50':>16}")
    for chat in CONVERSATIONS:
        rows = [r for r in results if r.chat == chat]
        if not rows:
            continue
        times = sorted(r.seconds for r in rows)
        firsts = [r.first_content_seconds for r in rows if r.first_content_seconds is not None]
        p95 = times[min(len(times) - 1, int(round(0.95 * (len(times) - 1))))]
        fails = sum(not r.ok for r in rows)
        first = f"{statistics.median(firsts):.1f}s" if firsts else "-"
        print(f"{chat:<8}{len(rows):>8}{fails:>7}{statistics.median(times):>7.1f}s"
              f"{p95:>7.1f}s{times[-1]:>7.1f}s{first:>16}")

    failed = [r for r in results if not r.ok]
    print()
    if failed:
        print(f"RESULT: FAIL. {len(failed)} of {len(results)} replies failed.")
        reasons = {}
        for r in failed:
            for f in r.failures:
                key = f.split(":")[0]
                reasons[key] = reasons.get(key, 0) + 1
        for key, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"  - {key}: {count}")
    else:
        print(f"RESULT: PASS. All {len(results)} replies passed.")
    return not failed


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--users", type=int, default=5, help="users at the same time on each chat")
    parser.add_argument("--max-seconds", type=float, default=10.0)
    parser.add_argument("--chats", nargs="+", choices=list(CONVERSATIONS), default=list(CONVERSATIONS))
    parser.add_argument("--together", action="store_true",
                        help="run all chats at the same time, not one chat after the other")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    run_id = time.strftime("%Y%m%d-%H%M%S")
    # The request timeout is longer than the target, so that a slow reply
    # shows its real time and is not cut off.
    timeout = httpx.Timeout(60.0, connect=15.0)
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=100)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        if not await wake_server(client, base):
            sys.exit(2)

        results = []
        if args.together:
            print(f"All chats together: {args.users} users on each chat.\n")
            groups = await asyncio.gather(*[
                run_user(client, base, chat, u, args.max_seconds, run_id)
                for chat in args.chats for u in range(args.users)
            ])
            results = [r for g in groups for r in g]
        else:
            for chat in args.chats:
                print(f"Chat '{chat}': {args.users} users at the same time.")
                groups = await asyncio.gather(*[
                    run_user(client, base, chat, u, args.max_seconds, run_id)
                    for u in range(args.users)
                ])
                results += [r for g in groups for r in g]
                print()

    passed = summarize(results, args.max_seconds)
    report = Path(__file__).with_name(f"load_test_report_{run_id}.json")
    report.write_text(json.dumps({
        "base_url": base, "users": args.users, "max_seconds": args.max_seconds,
        "together": args.together, "run_id": run_id, "passed": passed,
        "results": [asdict(r) for r in results],
    }, indent=2))
    print(f"\nReport: {report}")
    print(f"Test user IDs start with '{USER_PREFIX}-{run_id}-'.")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
