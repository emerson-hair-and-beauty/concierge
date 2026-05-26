import json
from typing import List, Dict

from google import genai
from app.config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY)

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
  - reassurance    : Seeking validation or feeling defeated. "I've tried everything, nothing works."
  - post_purchase  : Already bought, asking how to use or what to expect. "I got the product, now what?"
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
  - high     : Repeated confusion, resistance, frustration, or feeling unheard

emotional_state: What is the user's predominant emotional tone?
  - frustrated : Expressing annoyance, disappointment, or repeated failure
  - hopeful    : Optimistic, looking for a solution they believe exists
  - neutral    : Matter-of-fact, no strong emotional signal
  - fatigued   : Tired of trying, low energy, resigned tone

Conversation:
{conversation}"""

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "journey_state": {
            "type": "STRING",
            "enum": [
                "discovering", "diagnosing", "evaluating",
                "conversion_ready", "reassurance", "post_purchase", "troubleshooting"
            ]
        },
        "intent_clarity":   {"type": "STRING", "enum": ["low", "medium", "high"]},
        "confidence_level": {"type": "STRING", "enum": ["certain", "unsure", "overwhelmed"]},
        "friction_score":   {"type": "STRING", "enum": ["low", "moderate", "high"]},
        "emotional_state":  {"type": "STRING", "enum": ["frustrated", "hopeful", "neutral", "fatigued"]},
        "reasoning":        {"type": "STRING"},
    },
    "required": [
        "journey_state", "intent_clarity", "confidence_level",
        "friction_score", "emotional_state", "reasoning"
    ],
}

_GEMINI_CONFIG = {
    "response_mime_type": "application/json",
    "response_schema": _RESPONSE_SCHEMA,
}


async def detect_intent(messages: List[Dict[str, str]]) -> Dict:
    conversation = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content') or m.get('message', '')}"
        for m in messages
    )
    print(f"[IntentDetector] Conversation sent:\n{conversation}\n")

    try:
        response = await _client.aio.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=_DETECTION_PROMPT.format(conversation=conversation),
            config=_GEMINI_CONFIG,
        )
        print(f"[IntentDetector] Raw response: {response.text}")
        result = json.loads(response.text)
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
