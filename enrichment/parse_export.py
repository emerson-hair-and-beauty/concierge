"""Read a WhatsApp chat export and turn it into pipeline turns.

Why this exists
---------------
The business number runs in the WhatsApp Business app, not on the Cloud API. No
webhook delivers these conversations today, and Coexistence needs a Solution
Partner before one will. So the only real WhatsApp data available now is the
export the app writes: open a chat, choose "Export chat", choose "Without media".

That export is enough to answer the question that decides the design. The signal
detector was tuned on the chat pipeline, where the assistant is our own composer.
On WhatsApp the assistant is a person who restates the problem back:

    Agent: so the breakage started after you changed shampoo?

Nothing in the detection prompt says a signal must come from the customer. This
module gives you the transcript in both shapes, so you can measure whether that
matters instead of guessing.

Export formats
--------------
Two formats exist and both appear in the wild:

    Android   17/08/2026, 14:32 - Sarah: my hair is so dry
    iOS       [17/08/2026, 2:32:05 PM] Sarah: my hair is so dry

A message can run over several lines. Only the first line carries a timestamp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# iOS writes direction marks around the timestamp. They are invisible and they
# break every regex that does not remove them first.
_INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬﻿"), None)

_TIME = r"\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap]\.?[Mm]\.?)?"
_DATE = r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"

_ANDROID = re.compile(rf"^(?P<stamp>{_DATE},?\s+{_TIME})\s+-\s+(?P<rest>.*)$")
_IOS = re.compile(rf"^\[(?P<stamp>{_DATE},?\s+{_TIME})\]\s*(?P<rest>.*)$")

# Lines the app writes itself. They carry no customer text and must not become
# turns, or "Messages are end-to-end encrypted" becomes something to analyse.
_SYSTEM_MARKERS = (
    "end-to-end encrypted",
    "created group",
    "added you",
    "changed their phone number",
    "changed the subject",
    "joined using this group",
    "security code changed",
    "missed voice call",
    "missed video call",
)

# Placeholders that replace an attachment in a "Without media" export. They tell
# you a photo existed. They say nothing about hair, so they are dropped.
_MEDIA_MARKERS = (
    "<media omitted>",
    "image omitted",
    "video omitted",
    "audio omitted",
    "sticker omitted",
    "document omitted",
    "gif omitted",
    "contact card omitted",
    "this message was deleted",
    "you deleted this message",
    "null",
)

_EDITED = re.compile(r"\s*<this message was edited>\s*$", re.I)

# A sender name longer than this is almost always a system line that happens to
# contain a colon, not a person.
_MAX_SENDER_LEN = 60


@dataclass(frozen=True)
class Turn:
    """One message from one person."""

    stamp: str
    sender: str
    text: str
    # True when WhatsApp wrote "~Kety" rather than a saved contact name.
    #
    # This matters more than it looks. The tilde means the contact is NOT saved
    # in the agent's phone, so WhatsApp fell back to the name the CUSTOMER chose
    # for themselves. Without the tilde you are reading the agent's own label for
    # that contact, which is as likely to say "Mum" or "Noor DXB" as a real name.
    # So the tilde tells you whether the name is safe to write to a profile.
    is_profile_name: bool = False


def _clean(line: str) -> str:
    return line.translate(_INVISIBLE).rstrip("\n\r")


def _split_sender(rest: str) -> tuple[str, str, bool] | None:
    """Split "Sarah: my hair is dry" into the sender, the text, and the name source.

    Returns None when the line is a system notice rather than a message.
    """
    lowered = rest.lower()
    if any(marker in lowered for marker in _SYSTEM_MARKERS):
        return None
    if ": " not in rest:
        return None
    sender, text = rest.split(": ", 1)
    if len(sender) > _MAX_SENDER_LEN:
        return None
    sender = sender.strip()
    # Strip the tilde WhatsApp puts before an unsaved contact's profile name.
    # Left in place it reaches Klaviyo as first_name "~Kety".
    is_profile_name = sender.startswith("~")
    return sender.lstrip("~").strip(), text, is_profile_name


def parse_text(raw: str) -> list[Turn]:
    """Turn the contents of one export file into turns, in order."""
    turns: list[Turn] = []
    pending: list[str] = []
    stamp = sender = ""
    profile_name = False

    def flush() -> None:
        if not sender:
            return
        text = _EDITED.sub("", "\n".join(pending)).strip()
        if not text or text.lower() in _MEDIA_MARKERS:
            return
        turns.append(Turn(stamp=stamp, sender=sender, text=text, is_profile_name=profile_name))

    for line in raw.splitlines():
        line = _clean(line)
        match = _ANDROID.match(line) or _IOS.match(line)
        if not match:
            # No timestamp, so this continues the message above it.
            if sender:
                pending.append(line)
            continue

        flush()
        split = _split_sender(match.group("rest"))
        if split is None:
            stamp = sender = ""
            pending = []
            continue
        stamp = match.group("stamp")
        sender, first, profile_name = split
        pending = [first]

    flush()
    return turns


def read_export(path: Path) -> list[Turn]:
    """Read one export file. Falls back to a lenient decode for old exports."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    return parse_text(raw)


def find_exports(target: Path) -> list[Path]:
    """Accept a directory or a single file and return the export files."""
    if target.is_dir():
        return sorted(p for p in target.glob("*.txt") if p.is_file())
    return [target] if target.is_file() else []


def infer_agent(exports: dict[Path, list[Turn]]) -> str | None:
    """Guess which sender is the agent.

    The agent appears in every conversation. Each customer appears in one. So the
    sender present in the most files is the agent. This needs three or more files
    to mean anything; below that, pass the name yourself.
    """
    if len(exports) < 3:
        return None
    seen: dict[str, int] = {}
    for turns in exports.values():
        for name in {t.sender for t in turns}:
            seen[name] = seen.get(name, 0) + 1
    if not seen:
        return None
    name, count = max(seen.items(), key=lambda kv: kv[1])
    # Require the name in most files. A tie means the guess is not safe.
    return name if count >= max(3, len(exports) * 0.8) else None


def to_turns(turns: list[Turn], agent: str | None) -> list[dict[str, str]]:
    """Map turns onto the shape `detect_signals` expects.

    The agent becomes "assistant" and everyone else becomes "user". With no agent
    name, every turn becomes "user", which overstates what the customer said.
    """
    return [
        {
            "role": "assistant" if agent and t.sender == agent else "user",
            "content": t.text,
        }
        for t in turns
    ]


def customer_only(turns: list[dict[str, str]]) -> list[dict[str, str]]:
    return [t for t in turns if t["role"] == "user"]
