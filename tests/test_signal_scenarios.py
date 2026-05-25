"""
Signal detection scenario runner.
Plays through pre-scripted conversations and shows signal snapshots after each turn.
Covers primary detection, fallback triggers, and multi-signal cases.
"""

import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google import genai
from app.config import GEMINI_API_KEY
from app.services.session_signal.session_signal_service import process_session_signals

SESSION_COUNTER = 0

_HAIR_ASSISTANT_PROMPT = """\
You are a friendly hair care assistant. The user is describing their hair concerns.
Reply in 2-3 sentences only. Be conversational and ask one follow-up question.

Conversation so far:
{history}

User: {message}
Assistant:"""

SCENARIOS = [
    {
        "name": "Primary — Absorption Blocked",
        "description": "User clearly describes moisture not soaking in.",
        "turns": [
            "My hair feels like straw no matter what I do.",
            "I deep condition every single week and it still feels dry.",
        ],
    },
    {
        "name": "Primary — Hold Loss",
        "description": "User describes curls losing definition over time.",
        "turns": [
            "My wash day results are amazing but by day 2 everything falls flat.",
            "My curls frizz out really quickly, especially at the ends.",
        ],
    },
    {
        "name": "Primary — Breakage Active",
        "description": "User explicitly mentions shedding and weak strands.",
        "turns": [
            "I lose so much hair when I detangle, it's scary.",
            "My curls feel really weak and limp lately.",
        ],
    },
    {
        "name": "Primary — Buildup Present",
        "description": "User describes scalp itching and weighed-down hair.",
        "turns": [
            "My scalp has been really itchy and my hair feels heavy.",
            "Products don't seem to work the way they used to.",
        ],
    },
    {
        "name": "Fallback — Dry Scalp (Implicit Buildup)",
        "description": "User says 'my scalp is so dry' — no anchor match, fallback should infer buildup_present.",
        "turns": [
            "my scalp is so dry",
        ],
    },
    {
        "name": "Fallback — Implicit Breakage",
        "description": "User describes the situation (drain hair, thinner ponytail) without naming breakage.",
        "turns": [
            "I've been noticing a lot more hair in my shower drain lately.",
            "My ponytail feels thinner than it did a few months ago.",
        ],
    },
    {
        "name": "Fallback — Implicit Coated Feel",
        "description": "User describes products behaving differently without naming the signal.",
        "turns": [
            "My hair looks healthy but something just feels off when I touch it.",
            "Products I've used for years don't seem to do the same thing anymore.",
        ],
    },
    {
        "name": "Multi-Signal",
        "description": "User describes symptoms that span multiple signals at once.",
        "turns": [
            "My curls are breaking off and they never hold their shape.",
            "Nothing I put in my hair seems to absorb — it all just sits on top.",
        ],
    },
]


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


def print_snapshot(snapshot: dict):
    signal_keys = ["absorption_blocked", "hold_loss", "breakage_active", "buildup_present", "coated_feel"]
    active = [k for k in signal_keys if snapshot.get(k)]
    print("  ┌─ SIGNAL SNAPSHOT ──────────────────────────")
    for k in signal_keys:
        marker = "● ACTIVE" if snapshot.get(k) else "○ clear"
        print(f"  │  {k:<22} {marker}")
    print(f"  │  confidence:          {snapshot.get('confidence_score', 0.0):.2f}")
    print(f"  │  fallback used:       {'yes ◀' if snapshot.get('fallback_used') else 'no'}")
    if snapshot.get("evidence_quote"):
        print(f"  │  evidence: \"{snapshot['evidence_quote']}\"")
    if active:
        print(f"  │  active signals:      {', '.join(active)}")
    print("  └────────────────────────────────────────────")


async def run_scenario(index: int, scenario: dict):
    global SESSION_COUNTER
    SESSION_COUNTER += 1
    session_id = f"scenario-{SESSION_COUNTER}"
    user_id = "test-user"

    print(f"\n{'═' * 52}")
    print(f"  Scenario {index + 1}: {scenario['name']}")
    print(f"  {scenario['description']}")
    print(f"{'═' * 52}")

    history = []

    for user_message in scenario["turns"]:
        print(f"\n  You:  {user_message}")

        history.append({"role": "user", "message": user_message})

        snapshot = await process_session_signals(user_id, session_id, history)
        print()
        print_snapshot(snapshot)

        ai_reply = await get_ai_reply(history[:-1], user_message)
        print(f"\n  AI:   {ai_reply}")

        history.append({"role": "assistant", "message": ai_reply})

        await asyncio.sleep(0.5)


async def main():
    print("\n" + "═" * 52)
    print("  Signal Detection — Scenario Runner")
    print("  Press Ctrl+C to stop early")
    print("═" * 52)

    for i, scenario in enumerate(SCENARIOS):
        await run_scenario(i, scenario)
        await asyncio.sleep(1)

    print(f"\n{'═' * 52}")
    print(f"  Done. {len(SCENARIOS)} scenarios run.")
    print("═" * 52)


if __name__ == "__main__":
    asyncio.run(main())
