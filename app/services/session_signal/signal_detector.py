import json
from typing import List, Dict

from google import genai
from app.config import GEMINI_API_KEY

SIGNAL_NAMES = [
    "absorption_blocked",
    "hold_loss",
    "breakage_active",
    "buildup_present",
    "coated_feel",
]

_DETECTION_PROMPT = """\
Role: You are an expert Hair Health Analyst. Your goal is to map user complaints to specific hair health "Signals" with high precision.

Detection Instructions:
Analyze the conversation and identify ALL Signals that apply. Multiple signals can be active at the same time. If the user's description is vague or doesn't fit any signal, set all to false.
Be generous in your interpretation — users describe symptoms in casual, everyday language, not clinical terms.

Signal Definitions:

absorption_blocked: Products "bead up" or won't soak in despite the hair being clean. Focuses on the hair's inability to receive moisture.
  Example phrases: "nothing absorbs", "products just sit on top", "my hair won't drink anything", "so dry no matter what I use", "repelling moisture", "hydration won't penetrate"

hold_loss: Curls falling limp, styles not lasting, or hair feeling "mushy" and losing its shape. Focuses on structure and elasticity.
  Example phrases: "curls drop by noon", "no definition", "styles don't last", "hair goes flat", "loses shape fast", "no hold", "mushy", "limp"

breakage_active: Evidence of snapping, short hairs falling out (not from the root), or "haystack" ends. Focuses on physical integrity/damage.
  Example phrases: "hair keeps snapping", "lots of short pieces", "breaking off", "split ends everywhere", "hair feels weak", "snaps when I detangle", "shedding a lot"

buildup_present: Scalp itchiness, "gunk" under fingernails, or hair feeling dull/heavy due to layers of old product. Focuses on the need for cleansing.
  Example phrases: "scalp is itchy", "hair feels heavy", "product won't wash out", "dull and weighed down", "residue on scalp", "hair looks dirty fast", "gunky"

coated_feel: A waxy, plastic-like, or "filmy" texture usually caused by silicones or heavy oils. Focuses on the tactile texture of the hair strand.
  Example phrases: "waxy feeling", "hair feels coated", "plastic-like texture", "filmy", "silicone buildup", "hair doesn't feel like hair", "greasy but not moisturised"

Conversation:
{conversation}"""

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "absorption_blocked": {"type": "BOOLEAN"},
        "hold_loss":          {"type": "BOOLEAN"},
        "breakage_active":    {"type": "BOOLEAN"},
        "buildup_present":    {"type": "BOOLEAN"},
        "coated_feel":        {"type": "BOOLEAN"},
        "confidence_score": {"type": "NUMBER", "minimum": 0.0, "maximum": 1.0},
        "evidence_quote": {"type": "STRING"}
    },
    "required": SIGNAL_NAMES + ["confidence_score", "evidence_quote"],
}


async def detect_signals(messages: List[Dict[str, str]]) -> Dict[str, bool]:
    conversation = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content') or m.get('message', '')}"
        for m in messages
    )
    prompt = _DETECTION_PROMPT.format(conversation=conversation)

    print(f"[SignalDetector] Conversation sent:\n{conversation}\n")
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": _RESPONSE_SCHEMA,
            },
        )
        print(f"[SignalDetector] Raw response: {response.text}")
        result = json.loads(response.text)
        signals = {k: bool(result.get(k, False)) for k in SIGNAL_NAMES}
        signals["confidence_score"] = result.get("confidence_score", 0.0)
        signals["evidence_quote"] = result.get("evidence_quote", "")
        return signals
    except Exception as e:
        print(f"[SignalDetector] Error: {e}")
        return {k: False for k in SIGNAL_NAMES} | {"confidence_score": 0.0, "evidence_quote": ""}
