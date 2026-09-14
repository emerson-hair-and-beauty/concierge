"""Find the email address and the name in a conversation.

Why the email uses no model
---------------------------
An email address matches a pattern, so code finds it. A model can invent an
address the customer never typed, and a wrong address in a marketing profile
reaches a real person. The pattern cannot invent anything, costs nothing, and
runs at once.

The name is different. "I'm Sarah" and "my sister Sarah has the same problem"
look identical to a pattern. That is a judgment call, so the model takes it.

The obfuscated case
-------------------
Some people write "sarah at gmail dot com" to get past filters. The pattern does
not match that form. `count_obfuscated` measures how often it happens instead of
trying to parse it. Read the count first. Write more code only if the number
justifies it.
"""

from __future__ import annotations

import re

from app.agents.llm_call.provider import generate_json

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Deliberately loose. It only counts candidates for a measurement; it never
# produces an address to store.
_OBFUSCATED = re.compile(
    r"\b[\w.\-]+\s+(?:at|\(at\)|\[at\])\s+[\w.\-]+\s+(?:dot|\(dot\)|\[dot\])\s+\w{2,}\b",
    re.I,
)

_NAME_PROMPT = """\
Read the conversation. Find the first name of the CUSTOMER only.

The customer is the person marked USER. Take the name only when the customer
gives their own name. Do not take these:
- the name of anyone else the customer mentions (a sister, a friend, a child)
- the name of the agent marked ASSISTANT
- a brand, a product, or a place

Examples:
  "hi im sarah"                          -> Sarah
  "my sister sarah has the same problem" -> null
  "thanks Layla!"                        -> null   (that is the agent)
  "book it under Noor please"            -> Noor   (the customer names themselves)

Return only JSON:
{{"name": "<first name, or null>", "confidence": <0.0 to 1.0>, "evidence": "<the exact words, or empty>"}}

Conversation:
{conversation}"""


def find_emails(turns: list[dict[str, str]]) -> list[str]:
    """Every address the customer typed, in order. The agent's turns are ignored."""
    found: list[str] = []
    for turn in turns:
        if turn.get("role") != "user":
            continue
        for match in EMAIL.finditer(turn.get("content", "")):
            address = match.group(0).rstrip(".,;:!?)")
            if address not in found:
                found.append(address)
    return found


def pick_email(turns: list[dict[str, str]]) -> str | None:
    """The address to store: the last one the customer typed.

    Last, not first. A customer who mistypes an address types it again, and the
    correction is the one that counts.
    """
    found = find_emails(turns)
    return found[-1] if found else None


def count_obfuscated(turns: list[dict[str, str]]) -> int:
    """How many addresses the pattern probably missed. A measurement, not a value."""
    return sum(
        len(_OBFUSCATED.findall(turn.get("content", "")))
        for turn in turns
        if turn.get("role") == "user"
    )


async def find_name(turns: list[dict[str, str]]) -> dict:
    """Ask the model for the customer's first name. One call.

    Returns `{"name": str | None, "confidence": float, "evidence": str}`.
    On any failure it returns an empty result rather than a guess, because the
    caller writes this to a live customer profile.
    """
    conversation = "\n".join(
        f"{t.get('role', 'user').upper()}: {t.get('content', '')}" for t in turns
    )
    empty = {"name": None, "confidence": 0.0, "evidence": ""}
    if not conversation.strip():
        return empty

    try:
        result = await generate_json(_NAME_PROMPT.format(conversation=conversation))
    except Exception as e:
        print(f"[enrichment.contacts] name detection failed: {e}")
        return empty
    if not isinstance(result, dict):
        return empty

    name = result.get("name")
    if isinstance(name, str):
        name = name.strip() or None
    if not isinstance(name, str):
        name = None

    try:
        confidence = float(result.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "name": name,
        "confidence": confidence,
        "evidence": str(result.get("evidence") or ""),
    }
