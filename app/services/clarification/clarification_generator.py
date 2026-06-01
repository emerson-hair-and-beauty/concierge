import json
from typing import List, Dict

from google import genai
from app.config import GEMINI_API_KEY
from app.services.decision_state.models import ClarificationOption, ClarificationRequest

_client = genai.Client(api_key=GEMINI_API_KEY)

_PROMPT = """\
You are a friendly hair care expert helping a concierge understand what a customer is experiencing.

The customer said: "{user_message}"

We could not confidently identify their hair issue from that message alone. Your job is to write ONE short clarifying question and 3-4 answer options that will help us narrow it down.

Rules:
- The question must reference the customer's actual words (e.g. if they said "my hair has been acting up", ask "When you say your hair's been acting up, which of these sounds closest?")
- Each option must describe a concrete, physical hair experience in plain, everyday language — no clinical terms
- Write options as if a knowledgeable friend is speaking, not a medical form
- The final option must always be: "Not sure — it just feels off"
- Map each option to one of these signals (do not show the signal name to the user):
    absorption_blocked — hair won't absorb products or moisture despite being clean
    hold_loss          — curls lose shape or definition, styles don't last
    breakage_active    — hair snapping, shedding, short pieces breaking off
    buildup_present    — scalp feels heavy, itchy, or like products have stopped working
    coated_feel        — hair feels waxy, filmy, or coated even though it looks fine

Return valid JSON only:
{{
  "question": "...",
  "options": [
    {{"label": "...", "signal_hint": "signal_name_or_null"}},
    ...
  ]
}}"""

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "question": {"type": "STRING"},
        "options": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "label":       {"type": "STRING"},
                    "signal_hint": {"type": "STRING"},
                },
                "required": ["label"],
            },
        },
    },
    "required": ["question", "options"],
}

_GEMINI_CONFIG = {
    "response_mime_type": "application/json",
    "response_schema":    _RESPONSE_SCHEMA,
}


async def generate_clarification(messages: List[Dict]) -> ClarificationRequest:
    last_user_msg = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )

    try:
        response = await _client.aio.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=_PROMPT.format(user_message=last_user_msg),
            config=_GEMINI_CONFIG,
        )
        print(f"[ClarificationGenerator] Raw response: {response.text}")
        data = json.loads(response.text)

        options = [
            ClarificationOption(
                label=opt["label"],
                signal_hint=opt.get("signal_hint") or None,
            )
            for opt in data.get("options", [])
        ]
        return ClarificationRequest(question=data["question"], options=options)

    except Exception as e:
        print(f"[ClarificationGenerator] Error: {e}")
        return ClarificationRequest(
            question="Can you tell me a bit more about what's happening with your hair?",
            options=[
                ClarificationOption(label="Products sit on top — nothing absorbs",         signal_hint="absorption_blocked"),
                ClarificationOption(label="My curls lose shape or definition quickly",     signal_hint="hold_loss"),
                ClarificationOption(label="Hair is snapping or shedding more than usual",  signal_hint="breakage_active"),
                ClarificationOption(label="Scalp feels heavy, itchy, or products stopped working", signal_hint="buildup_present"),
                ClarificationOption(label="Not sure — it just feels off",                  signal_hint=None),
            ],
        )
