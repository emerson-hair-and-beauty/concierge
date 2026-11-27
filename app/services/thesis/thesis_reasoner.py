"""
Thesis step: test the decision engine's path before the concierge gives advice.

The decision engine picks a path (for example reset_first). That path is the thesis.
The model does not choose the thesis. It picks the strongest rival from a fixed list
of engine paths, decides if one question can tell the two apart, and writes the
words: the thesis, the rival, the question, and the tap options.

The code, not the model, decides if the concierge asks. This keeps the limits fixed:
one question per turn, and a maximum of MAX_QUESTIONS questions in a row before the
concierge gives advice. After the guest answers, the engine runs again on the full
chat. If the answer changes the path, the thesis changes with it.

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
from app.services.decision_state.response_composer import _DECISION_EXPLANATIONS

THESIS_CLARIFY = os.getenv("THESIS_CLARIFY", "1") == "1"
MAX_QUESTIONS = 2

# Engine paths that name a cause, so the concierge can test them with a question.
# reinforce_current_routine and simplify_and_reduce_friction do not name a cause:
# when the engine picks one of them, the concierge gives advice without a question.
THESIS_PATHS = {
    "repair_first":              "damage: weak, broken, or overworked hair (heat, colour, tension, rough handling)",
    "reset_first":               "buildup: product, oil, or hard water residue that sits on the hair or scalp",
    "scalp_calm_first":          "a sensitive scalp: the scalp reacts to products, friction, or the wash routine",
    "hold_and_definition_first": "hold: the styling products or method do not hold the curl",
    "climate_control_first":     "climate: humidity, heat, or air conditioning works against the hair",
    "balanced_routine_first":    "routine balance: the wash, moisture, and styling steps are out of balance",
}

# Rivals are the paths that the guest's answer can move the engine to. The signal
# step turns the chat into these paths. Climate and routine balance come only from
# the saved profile and the weather, so an answer in the chat cannot move the engine
# there. A question about them cannot change the advice.
RIVAL_PATHS = ("repair_first", "reset_first", "scalp_calm_first", "hold_and_definition_first")

# Questions asked in a row for each session. The count goes back to 0 when the
# concierge gives advice. It lives in memory, like the advisor chat history.
_questions_in_a_row: Dict[str, int] = {}

# The lead-in for the first question: the guest's symptoms and the two causes.
_FIRST_LEAD_IN = """9. lead_in: ONE sentence an expert says before the question. It names the guest's \
symptoms and the two causes that usually give them: the THESIS first, then the rival. \
Pattern: "<their symptoms> usually comes from one of two things: <thesis cause>, or \
<rival cause>."
   - Use every symptom in "symptoms", and no symptom that is not in it. Never add a \
feeling or a symptom the guest did not say (for example "irritated", "uncomfortable", \
"itchy").
   - Describe each cause as a habit, a product, or something on the hair. Never say \
that something is wrong with the guest's skin or body, and never tell the guest what \
their hair or scalp "is".
   - Never use hedge words: "maybe", "might", "could", "possibly", "perhaps", "I think", \
"my guess", "it sounds like", "it seems", "can", "may", "suggests", "often". No technical \nterms."""

# The lead-in for a follow-up question: what the last answer showed. The two causes
# are already on screen, so the concierge does not repeat them.
_FOLLOW_UP_LEAD_IN = """9. lead_in: the concierge already asked a question, and the guest answered it. Do NOT repeat the symptoms or the two causes. Write ONE short sentence that says what the guest's last answer shows, in plain expert words. Example: "Itching that builds up over a few days points to residue." Then the question follows.
   - Use only what the guest said. Never add a feeling or a symptom.
   - Never use hedge words: "maybe", "might", "could", "possibly", "perhaps", "I think", "my guess", "it sounds like", "it seems", "can", "may", "suggests", "often". No technical \nterms."""

_PROMPT = """\
You write for Emerson, a hair care concierge for curly and textured hair in the GCC. \
The decision engine already chose the most likely cause. That cause is the THESIS. \
Do not change it, and do not add a cause of your own.

THESIS (engine path {thesis_path}): {thesis_plain}
Engine notes for this path:
{thesis_notes}

RIVALS you can choose from (engine path: meaning):
{rivals}

SAVED PROFILE (from onboarding; "Unspecified" means unknown, and medium porosity may be a default):
- texture: {texture}
- porosity: {porosity}
- density: {density}
- hard water where they live: {hard_water}
- chemically treated (colour, relaxer, perm): {chemical}
- scalp type: {scalp}
- how the hair reacts to humidity: {humidity}
- hair goals: {goals}

CONVERSATION (oldest first):
{conversation}

The concierge has asked {asked} question(s) in a row. It can ask at most {max_q} in a row.

Think it through:
1. rival: the engine path from the RIVALS list that best fits the guest's words. Use \
the path name exactly as written.
2. deciding_fact: one fact about the guest's life or routine that is true under the \
thesis and false under the rival. Prefer lifestyle and routine facts: how often they \
wash, the products they use, exercise or swimming, time in air conditioning, heat \
styling, protective styles.
3. already_known: facts the guest already gave, and every known fact in SAVED PROFILE. Never ask about these. Use them: for example, if the profile says the hair is chemically treated, do not ask about colour or chemical work; treat it as known. Choose the deciding fact among the things that are still unknown.
4. confidence: "high" if the conversation already rules out the rival, "medium" if the \
thesis is likely but the rival is still open, "low" if you cannot tell.
5. decision: "ask" or "advise". Picture an expert at the Emerson counter.
   - "ask" when the guest names a symptom but not enough about their routine or life \
to choose between the thesis and the rival.
   - "advise" when the guest already gave enough to confirm the thesis, when the \
question is not about their hair (store, delivery, price), or when the answer would \
not change the first step.
   A guest who asks "what should I use?" still gets a question if the rival is open. \
Experts ask before they recommend.
6. decision_reason: one short sentence that explains the decision.
7. user_wants_answer: true ONLY if the guest refuses questions or shows impatience: \
"just tell me", "no questions", or they repeat a request for a recommendation after \
the concierge already asked. Asking for help is not impatience.
8. symptoms: the symptoms the guest said, in their own words. Nothing else.
{lead_in_rule}
   NO SYMPTOMS: if "symptoms" is empty and the guest's message is about their hair, \
there is nothing to test yet. Then decision is "ask", lead_in is "", the question asks \
what they notice about their hair in one warm, open sentence, and the options are 2 to \
4 common problems in everyday words: for example dry or breaking hair, hair that feels \
coated, a scalp that bothers them, curls that do not hold. If the message is not about \
their hair (store, delivery, price), decision is "advise".
10. question: ONE question about ONE fact: the deciding fact. One sentence. Never ask \
two things in one question. Do not apologise. Do not give advice in the question.
11. options: 2 to 4 short answers the guest can tap. Each one must point toward the \
thesis or the rival. Plain, everyday words.

Never name a skin disease, a medical condition, a deficiency, or hormones.

Return JSON with exactly these keys:
{{"rival": str, "deciding_fact": str, "already_known": [str], \
"confidence": "low"|"medium"|"high", "decision": "ask"|"advise", "decision_reason": str, \
"user_wants_answer": bool, "symptoms": [str], "lead_in": str, "question": str, \
"options": [str]}}"""


def build_prompt(
    messages: List[Dict[str, str]],
    profile: ProfileState,
    env: EnvironmentalContext,
    asked: int,
    thesis_path: str,
) -> str:
    conversation = "\n".join(
        f"{'GUEST' if m.get('role') == 'user' else 'CONCIERGE'}: {m.get('content', '')}"
        for m in messages[-10:]
    )
    rivals = "\n".join(f"- {p}: {THESIS_PATHS[p]}" for p in RIVAL_PATHS if p != thesis_path)
    return _PROMPT.format(
        thesis_path=thesis_path,
        thesis_plain=THESIS_PATHS.get(thesis_path, "no cause found yet. If the guest names symptoms, decision is \"advise\""),
        thesis_notes=_DECISION_EXPLANATIONS.get(thesis_path, "") if thesis_path in THESIS_PATHS else "(none)",
        rivals=rivals,
        texture=profile.texture_label,
        porosity=profile.porosity,
        density=profile.density,
        hard_water="yes" if env.hard_water else "unknown",
        chemical=profile.chemical_treatment or "unknown",
        scalp=profile.scalp_state or "unknown",
        humidity=profile.humidity_response or "unknown",
        goals=", ".join(profile.hair_goals) if profile.hair_goals else "unknown",
        conversation=conversation,
        asked=asked,
        max_q=MAX_QUESTIONS,
        lead_in_rule=_FOLLOW_UP_LEAD_IN if asked else _FIRST_LEAD_IN,
    )


def should_ask(reasoning: Dict, asked: int) -> bool:
    """The rules for a question. The model gives its view; the code decides."""
    if asked >= MAX_QUESTIONS:
        return False                      # never ask more than MAX_QUESTIONS in a row
    if reasoning.get("user_wants_answer"):
        return False                      # the guest wants advice now
    if reasoning.get("decision") != "ask":
        return False                      # the model sees enough to advise, or a question would change nothing
    if not reasoning.get("question") or len(reasoning.get("options") or []) < 2:
        return False                      # a question needs text and tap options
    if not reasoning.get("symptoms"):
        return True                       # no hair problem named yet: ask what they notice
    if reasoning.get("thesis") not in THESIS_PATHS:
        return False                      # the engine path names no cause to test
    if reasoning.get("rival") not in RIVAL_PATHS or reasoning.get("rival") == reasoning.get("thesis"):
        return False                      # the rival must be another engine path
    if reasoning.get("confidence") == "high":
        return False                      # the rival is already ruled out
    return bool(reasoning.get("lead_in"))  # a question without a lead-in feels abrupt


def question_text(reasoning: Dict) -> str:
    """The lead-in (the guest's symptoms and the two causes), then the question, as one message."""
    parts = [reasoning.get("lead_in"), reasoning.get("question")]
    text = " ".join(p.strip() for p in parts if p and p.strip())
    return text[:1].upper() + text[1:]   # the lead-in can start with the guest's own lower-case words


async def run_thesis_step(
    session_id: str,
    messages: List[Dict[str, str]],
    profile: ProfileState,
    env: EnvironmentalContext,
    decision_state: str | None,
) -> tuple[Dict, ClarificationRequest | None]:
    """Return the reasoning, and a question if the concierge must ask one.
    If the model call fails, return no question, so the concierge gives advice as before."""
    asked = _questions_in_a_row.get(session_id, 0)
    if asked >= MAX_QUESTIONS:
        # The concierge gives advice now. Skip the model call, so the guest does not wait for it.
        _questions_in_a_row[session_id] = 0
        return {}, None
    try:
        reasoning = await generate_reasoning_json(build_prompt(messages, profile, env, asked, decision_state))
    except Exception as e:
        print(f"[Thesis] Reasoning failed, the concierge gives advice without it: {e}")
        return {}, None

    reasoning["thesis"] = decision_state   # the engine's path, never the model's
    print(f"[Thesis] asked={asked} reasoning={reasoning}")
    if should_ask(reasoning, asked):
        _questions_in_a_row[session_id] = asked + 1
        question = ClarificationRequest(
            question=question_text(reasoning),
            options=[ClarificationOption(label=o) for o in reasoning["options"][:4]],
        )
        return reasoning, question

    _questions_in_a_row[session_id] = 0
    return reasoning, None
