"""
Save every answer to a thesis question, also the answers the engine cannot use.

When the concierge asks a question, the question waits here in memory. On the next
turn, the guest's message is the answer: one row goes to Supabase with the thesis,
the question, the answer, and the engine path after the answer. path_changed is
false when the answer did not move the engine. Those rows show which answers the
engine has no signal or path for.

A failed write never stops the chat. The table lets the app add rows but not read
them (see sql/create_thesis_answers.sql).
"""
from typing import Dict, List

from app.services.resilience import safe_call
from app.services.supabase_service import get_supabase

TABLE = "thesis_answers"

# The last question asked in each session, until the guest answers it.
_pending: Dict[str, Dict] = {}


def remember_question(session_id: str, reasoning: Dict, question: str, options: List[str]) -> None:
    _pending[session_id] = {
        "thesis": reasoning.get("thesis"),
        "rival": reasoning.get("rival"),
        "question": question,
        "options": options,
    }


def take_pending(session_id: str) -> Dict | None:
    """Return the question the guest answers on this turn, and forget it."""
    return _pending.pop(session_id, None)


def save_answer(
    user_id: str,
    session_id: str,
    pending: Dict,
    answer: str,
    path_after: str | None,
    signals_after: List[str],
) -> None:
    def _write() -> None:
        get_supabase().table(TABLE).insert({
            "user_id": user_id,
            "session_id": session_id,
            "thesis": pending["thesis"],
            "rival": pending["rival"],
            "question": pending["question"],
            "options": pending["options"],
            "answer": answer,
            "path_after": path_after,
            "path_changed": path_after != pending["thesis"],
            "signals_after": signals_after,
        }, returning="minimal").execute()   # minimal: the app cannot read the table back

    safe_call(
        _write,
        fallback=None,
        source="thesis_answers.save_answer",
        detail=f"Could not save the answer to a thesis question for session={session_id!r}.",
    )
