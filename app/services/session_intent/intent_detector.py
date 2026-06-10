from typing import List, Dict

from app.agents.llm_call.provider import generate_json

_DETECTION_PROMPT = """\
Role: You are an expert conversation analyst for a hair care concierge service.

Analyse the conversation below and classify the user's current engagement state across five dimensions.
Be honest — if signals are mixed or unclear, reflect that in lower clarity scores.

Dimensions to detect:

journey_state: Where is the user in their journey?
  - discovering    : Exploring broadly, no specific concern yet. "I want to learn more about my hair."
  - diagnosing     : Describing a specific problem, seeking root cause. "My hair keeps breaking off."
  - evaluating     : Comparing options or weighing a recommendation. "Should I use X or Y?"
  - conversion_ready : Ready to buy, asking for a direct recommendation. "What should I get?"
  - reassurance    : Seeking validation that their approach is right, OR expressing satisfaction with current results and wanting confirmation to continue. "I've tried everything, nothing works." OR "My routine is working well, am I on the right track?"
  - post_purchase  : Already bought a specific product and asking how to use it or what to expect from it. Must involve a direct usage question about a product they mention acquiring. "I got the product, now what?" NOT for general satisfaction with a routine that is working.
  - troubleshooting: Routine failed or produced unexpected results. "I followed the routine and it made it worse."

intent_clarity: How clear is the user about what they want?
  - low    : Vague, unfocused, or emotionally driven message
  - medium : Some clarity but still exploring or uncertain
  - high   : Direct, specific, actionable question

confidence_level: How confident does the user feel about their hair knowledge?
  - certain     : Assured language, knows their hair well
  - unsure      : Hesitant, asking basic questions, qualifying statements
  - overwhelmed : Expressed confusion, too many problems at once, defeated tone

friction_score: How much resistance or difficulty is the user experiencing?
  - low      : Smooth engagement, open to suggestions
  - moderate : Some hesitation, mild pushback, or unanswered questions
  - high     : Repeated confusion, resistance, frustration, feeling unheard, OR an explicit request to simplify — e.g. "too many steps", "I want something simple", "I cannot deal with complicated", "just tell me what to do"

emotional_state: What is the user's predominant emotional tone?
  - frustrated : Expressing annoyance, disappointment, or repeated failure
  - hopeful    : Optimistic, looking for a solution they believe exists
  - neutral    : Matter-of-fact, no strong emotional signal
  - fatigued   : Tired of trying, low energy, resigned tone

Return a JSON object with keys: journey_state, intent_clarity, confidence_level, friction_score, emotional_state, reasoning.

Conversation:
{conversation}"""


async def detect_intent(messages: List[Dict[str, str]]) -> Dict:
    conversation = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content') or m.get('message', '')}"
        for m in messages
    )
    print(f"[IntentDetector] Conversation sent:\n{conversation}\n")

    try:
        result = await generate_json(_DETECTION_PROMPT.format(conversation=conversation))
        print(f"[IntentDetector] Raw response: {result}")
        return {
            "journey_state":    result.get("journey_state", "discovering"),
            "intent_clarity":   result.get("intent_clarity", "low"),
            "confidence_level": result.get("confidence_level", "unsure"),
            "friction_score":   result.get("friction_score", "low"),
            "emotional_state":  result.get("emotional_state", "neutral"),
            "reasoning":        result.get("reasoning", ""),
        }

    except Exception as e:
        print(f"[IntentDetector] Error: {e}")
        return {
            "journey_state":    "discovering",
            "intent_clarity":   "low",
            "confidence_level": "unsure",
            "friction_score":   "low",
            "emotional_state":  "neutral",
            "reasoning":        "",
        }
