"""
Thesis step: think before the concierge gives advice.

A reasoning model reads the conversation and writes a thesis (the most likely
cause), one or two rival causes, the fact that separates them, and one question
that tests that fact. The code, not the model, decides if the concierge asks the
question. This keeps the limits fixed: one question per turn, and a maximum of
MAX_QUESTIONS questions in a row before the concierge gives advice.

The step is on by default. Set THESIS_CLARIFY=0 to turn it off. When it is off,
the pipeline uses the old clarification gate.
"""
import os
from typing import Dict, List

from app.agents.llm_call.provider import generate_reasoning_json
from app.services.decision_state.models import (
    ClarificationOption,
    ClarificationRequest,
    EnvironmentalContext,
    ProfileState,
)
from app.services.decision_state.response_composer import FIXED_SECTION_DEFAULTS

THESIS_CLARIFY = os.getenv("THESIS_CLARIFY", "1") == "1"
MAX_QUESTIONS = 2

# Questions asked in a row for each session. The count goes back to 0 when the
# concierge gives advice. It lives in memory, like the advisor chat history.
_questions_in_a_row: Dict[str, int] = {}

_PROMPT = """\
You are the diagnostic mind of Emerson, a hair care concierge for curly and textured hair \
in the GCC. Before the concierge gives advice, you decide what is most likely happening, \
and whether one question would change the advice.

Reason from first principles. Use the guest's own words as evidence. These patterns are \
known to be true, and you can build on them:
{knowledge}

SAVED PROFILE (from onboarding; "Unspecified" means unknown, and medium porosity may be a default):
- texture: {texture}
- porosity: {porosity}
- density: {density}
- hard water where they live: {hard_water}

CONVERSATION (oldest first):
{conversation}

The concierge has asked {asked} question(s) in a row. It can ask at most {max_q} in a row.

Think it through:
1. thesis: the single most likely cause of what the guest describes.
2. rival_causes: one or two other causes that also fit the guest's words. Real alternatives, \
not small variations of the thesis.
3. deciding_fact: one fact about the guest's life or routine that is true under the thesis \
and false under a rival. Prefer lifestyle and routine facts: how often they wash, the products \
they use, exercise or swimming, time in air conditioning, heat styling, protective styles.
4. already_known: facts the guest already gave. Never ask about these again.
5. confidence: "high" if the conversation already rules out the rivals, "medium" if the \
thesis is likely but a rival is still open, "low" if you cannot tell.
6. decision: "ask" or "advise". Picture an expert at the Emerson counter.
   - "ask" when the guest names a symptom but not enough about their routine or life to \
choose between the thesis and a rival, and the right first step differs between them.
   - "advise" when the guest already gave their routine, products, or history and that is \
enough to pick a first step, when the question is not about their hair (store, delivery, \
price), or when the same first step is right under the thesis and every rival.
   A guest who asks "what should I use?" still gets a question if the cause is open. \
Experts ask before they recommend.
7. decision_reason: one short sentence that explains the decision.
8. user_wants_answer: true ONLY if the guest refuses questions or shows impatience: "just \
tell me", "no questions", or they repeat a request for a recommendation after the concierge \
already asked. Asking for help is not impatience.
9. question: ONE question that tests the deciding fact. Write it the way an expert at the \
Emerson counter would say it: name what you suspect and the rival in a few plain words, \
then ask. Maximum 2 short sentences. No technical terms. Do not repeat their words back \
to them. Do not apologise. Do not give advice in the question.
10. options: 2 to 4 short answers the guest can tap. Each one must point toward the thesis \
or a rival. Plain, everyday words.

Return JSON with exactly these keys:
{{"thesis": str, "rival_causes": [str], "deciding_fact": str, "already_known": [str], \
"confidence": "low"|"medium"|"high", "decision": "ask"|"advise", "decision_reason": str, \
"user_wants_answer": bool, "question": str, "options": [str]}}"""


def build_prompt(messages: List[Dict[str, str]], profile: ProfileState, env: EnvironmentalContext, asked: int) -> str:
    conversation = "\n".join(
        f"{'GUEST' if m.get('role') == 'user' else 'CONCIERGE'}: {m.get('content', '')}"
        for m in messages[-10:]
    )
    return _PROMPT.format(
        knowledge=FIXED_SECTION_DEFAULTS["diagnostic_reasoning_block"],
        texture=profile.texture_label,
        porosity=profile.porosity,
        density=profile.density,
        hard_water="yes" if env.hard_water else "unknown",
        conversation=conversation,
        asked=asked,
        max_q=MAX_QUESTIONS,
    )


def should_ask(reasoning: Dict, asked: int) -> bool:
    """The rules for a question. The model gives its view; the code decides."""
    if asked >= MAX_QUESTIONS:
        return False                      # never ask more than MAX_QUESTIONS in a row
    if reasoning.get("user_wants_answer"):
        return False                      # the guest wants advice now
    if reasoning.get("confidence") == "high":
        return False                      # the rivals are already ruled out
    if reasoning.get("decision") != "ask":
        return False                      # the model sees enough to advise, or a question would change nothing
    return bool(reasoning.get("question")) and len(reasoning.get("options") or []) >= 2


async def run_thesis_step(
    session_id: str,
    messages: List[Dict[str, str]],
    profile: ProfileState,
    env: EnvironmentalContext,
) -> tuple[Dict, ClarificationRequest | None]:
    """Return the reasoning, and a question if the concierge must ask one.
    If the model call fails, return no question, so the concierge gives advice as before."""
    asked = _questions_in_a_row.get(session_id, 0)
    if asked >= MAX_QUESTIONS:
        # The concierge must give advice now. Skip the model call, so the guest does not wait for it.
        _questions_in_a_row[session_id] = 0
        return {}, None
    try:
        reasoning = await generate_reasoning_json(build_prompt(messages, profile, env, asked))
    except Exception as e:
        print(f"[Thesis] Reasoning failed, the concierge gives advice without it: {e}")
        return {}, None

    print(f"[Thesis] asked={asked} reasoning={reasoning}")
    if should_ask(reasoning, asked):
        _questions_in_a_row[session_id] = asked + 1
        question = ClarificationRequest(
            question=reasoning["question"],
            options=[ClarificationOption(label=o) for o in reasoning["options"][:4]],
        )
        return reasoning, question

    _questions_in_a_row[session_id] = 0
    return reasoning, None
