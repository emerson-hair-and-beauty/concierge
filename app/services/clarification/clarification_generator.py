from typing import List, Dict

from app.agents.llm_call.provider import generate_json
from app.services.decision_state.models import ClarificationOption, ClarificationRequest

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

Return a JSON object with keys "question" (string) and "options" (array of objects with "label" and "signal_hint")."""


async def generate_clarification(messages: List[Dict]) -> ClarificationRequest:
    last_user_msg = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )

    try:
        data = await generate_json(_PROMPT.format(user_message=last_user_msg))
        print(f"[ClarificationGenerator] Raw response: {data}")

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
                ClarificationOption(label="Products sit on top — nothing absorbs",                signal_hint="absorption_blocked"),
                ClarificationOption(label="My curls lose shape or definition quickly",            signal_hint="hold_loss"),
                ClarificationOption(label="Hair is snapping or shedding more than usual",         signal_hint="breakage_active"),
                ClarificationOption(label="Scalp feels heavy, itchy, or products stopped working", signal_hint="buildup_present"),
                ClarificationOption(label="Not sure — it just feels off",                         signal_hint=None),
            ],
        )
