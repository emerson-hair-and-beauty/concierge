import asyncio
import sys
import os
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google import genai
from app.config import GEMINI_API_KEY
from app.services.session_signal.session_signal_service import process_session_signals

SESSION_ID = f"test-session-{uuid.uuid4().hex[:8]}"
USER_ID = "test-user-001"

_HAIR_ASSISTANT_PROMPT = """\
You are a friendly hair care assistant. The user is describing their hair concerns.
Reply in 2-3 sentences only. Be conversational and ask one follow-up question.

Conversation so far:
{history}

User: {message}
Assistant:"""


async def get_ai_reply(history: list, user_message: str) -> str:
    history_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['message']}"
        for m in history
    )
    prompt = _HAIR_ASSISTANT_PROMPT.format(history=history_text, message=user_message)

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config={"max_output_tokens": 120},
    )
    return (response.text or "").strip()


def print_signals(snapshot: dict):
    signal_keys = ["absorption_blocked", "hold_loss", "breakage_active", "buildup_present", "coated_feel"]
    active = [k for k in signal_keys if snapshot.get(k)]
    print("\n┌─ SIGNAL SNAPSHOT ──────────────────────────")
    for k in signal_keys:
        marker = "● ACTIVE" if snapshot.get(k) else "○ clear"
        print(f"│  {k:<22} {marker}")
    print(f"│  confidence:          {snapshot.get('confidence_score', 0.0):.2f}")
    if snapshot.get("evidence_quote"):
        print(f"│  evidence: \"{snapshot['evidence_quote']}\"")
    if active:
        print(f"│  Fired this session: {', '.join(active)}")
    print("└────────────────────────────────────────────\n")


async def main():
    history = []

    print("=" * 48)
    print("  Session Signal Test")
    print(f"  Session ID : {SESSION_ID}")
    print(f"  User ID    : {USER_ID}")
    print("  Type 'quit' to exit")
    print("=" * 48)

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("Session ended.")
            break
        if not user_input:
            continue

        history.append({"role": "user", "message": user_input})

        snapshot = await process_session_signals(USER_ID, SESSION_ID, history)
        print_signals(snapshot)

        ai_reply = await get_ai_reply(history[:-1], user_input)
        print(f"Assistant: {ai_reply}")
        history.append({"role": "assistant", "message": ai_reply})


if __name__ == "__main__":
    asyncio.run(main())
