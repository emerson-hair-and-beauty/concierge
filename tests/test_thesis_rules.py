"""
The rules that decide if the concierge asks a question (thesis_reasoner.should_ask).

Why these rules matter: the concierge must ask when a question can change the advice,
and it must not question the guest without end. A guest who gets 3 questions in a row,
or a question after "just tell me", has a worse experience than a guest who gets a best
guess. These tests fail if a change lets the model's view override those limits.

Run: python tests/test_thesis_rules.py
"""
import sys
sys.path.insert(0, ".")

from app.services.thesis.thesis_reasoner import MAX_QUESTIONS, should_ask

OPEN = {
    "confidence": "medium",
    "decision": "ask",
    "user_wants_answer": False,
    "question": "How often do you wash?",
    "options": ["Every day", "Once a week"],
}


def case(label, reasoning, asked, expected):
    got = should_ask(reasoning, asked)
    print(f"{'PASS' if got == expected else 'FAIL'}  {label}")
    return got == expected


results = [
    # The core reason for the feature: an open thesis gets a question.
    case("open thesis, no questions yet -> ask", OPEN, 0, True),
    case("open thesis, one question asked -> ask again", OPEN, 1, True),
    # The limit holds even when the model still wants to ask.
    case("limit reached -> give advice", OPEN, MAX_QUESTIONS, False),
    # The guest's wish beats the model's doubt.
    case("guest wants an answer -> give advice", {**OPEN, "user_wants_answer": True}, 0, False),
    # No question when the rivals are already ruled out.
    case("high confidence -> give advice", {**OPEN, "confidence": "high"}, 0, False),
    # The model sees enough to advise, or a question would not change the first step.
    case("model decides to advise -> give advice", {**OPEN, "decision": "advise"}, 0, False),
    # A question needs tap options, or the guest cannot answer it quickly.
    case("fewer than 2 options -> give advice", {**OPEN, "options": ["Every day"]}, 0, False),
    case("no question text -> give advice", {**OPEN, "question": ""}, 0, False),
    # A failed model call returns {}: the concierge must still answer.
    case("empty reasoning -> give advice", {}, 0, False),
]

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
