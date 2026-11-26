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
    "thesis": "reset_first",
    "rival": "scalp_calm_first",
    "confidence": "medium",
    "decision": "ask",
    "user_wants_answer": False,
    "symptoms": ["oily roots", "dry ends"],
    "lead_in": "Oily roots with dry ends usually come from one of two things: residue on the scalp, or a harsh wash.",
    "question": "How often do you wash?",
    "options": ["Every day", "Once a week"],
}

# No hair problem named yet. The engine path then names no cause, for example reinforce_current_routine.
NO_SYMPTOMS = {**OPEN, "symptoms": [], "lead_in": "", "rival": None, "thesis": "reinforce_current_routine"}


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
    # The thesis must be the engine's path, and the path must name a cause.
    case("symptoms, but the engine path names no cause -> give advice", {**OPEN, "thesis": "reinforce_current_routine"}, 0, False),
    # The rival must be another engine path that an answer can move the engine to.
    case("rival made up by the model -> give advice", {**OPEN, "rival": "a skin condition"}, 0, False),
    case("rival same as thesis -> give advice", {**OPEN, "rival": "reset_first"}, 0, False),
    case("rival the chat cannot reach -> give advice", {**OPEN, "rival": "climate_control_first"}, 0, False),
    # The guest must hear why the concierge asks. A bare question feels abrupt.
    case("no lead-in -> give advice", {**OPEN, "lead_in": ""}, 0, False),
    # No hair problem named yet: the concierge asks what the guest notices, with no lead-in.
    case("no symptoms -> ask what they notice", NO_SYMPTOMS, 0, True),
    case("no symptoms, limit reached -> give advice", NO_SYMPTOMS, MAX_QUESTIONS, False),
    case("no symptoms, not about hair -> give advice", {**NO_SYMPTOMS, "decision": "advise"}, 0, False),
    # A failed model call returns {}: the concierge must still answer.
    case("empty reasoning -> give advice", {}, 0, False),
]

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
