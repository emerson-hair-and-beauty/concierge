from typing import List, Dict

from app.agents.llm_call.provider import generate_json

SIGNAL_NAMES = [
    "absorption_blocked",
    "hold_loss",
    "breakage_active",
    "buildup_present",
    "coated_feel",
    "scalp_sensitivity",
]

_DETECTION_PROMPT = """\
Role: You are an expert Hair Health Analyst. Your goal is to map user complaints to specific hair health "Signals" with high precision.

Detection Instructions:
Analyze the conversation and identify ALL Signals that apply. Multiple signals can be active at the same time. If the user's description is vague or doesn't fit any signal, set all to false.
Be generous in your interpretation — users describe symptoms in casual, everyday language, not clinical terms.

Signal Definitions:

absorption_blocked: Products physically sit on the hair surface and cannot penetrate — the hair actively repels moisture or product despite being clean. Flag when the user has tried products and they are not working, regardless of whether they name the mechanism.
  Example phrases: "nothing absorbs", "products just sit on top", "my hair won't drink anything", "repelling moisture", "hydration won't penetrate", "dry after washing and conditioning even with heavy products", "nothing seems to work no matter what I apply", "curls never feel fully clean after cleansing", "moisture just bounces off", "I've tried everything and nothing works", "tried curl creams and leave-ins but still dry", "doesn't stay moisturised no matter what I use", "brittle even after conditioning"
  DO NOT flag for: general dryness the user attributes to climate, heat, or AC — only dismiss when the user explicitly names an external cause. If they have tried multiple products with no result, flag it.

hold_loss: Curls falling limp, styles not lasting, or hair losing shape and definition over time. Focuses on structure, elasticity, and style longevity.
  Example phrases: "curls drop by noon", "no definition", "styles don't last", "hair goes flat", "loses shape fast", "no hold", "mushy", "limp", "my curls lose definition quickly", "my curls frizz a few hours after wash day", "curls frizz quickly", "curls lose definition quickly especially at the ends", "curls don't clump properly", "styling gel doesn't define my curls for long", "I don't feel or see much of a cast after styling", "after day 2 or day 3 my curls look messy", "curls look frizzy in the morning", "curls frizz after diffusing", "wash day results only last a few days"

breakage_active: Evidence of snapping, excessive shedding, thinning, or weak strands. Focuses on physical integrity and structural damage to the hair shaft.
  Example phrases: "hair keeps snapping", "lots of short pieces", "breaking off", "split ends everywhere", "hair feels weak", "snaps when I detangle", "shedding a lot", "hairfall", "hair loss", "my hair isn't growing", "curls are thinning", "major hair fall when I brush my curls", "hair loss when detangling", "curls are weak or limp"
  DO NOT flag for: "brittle" used alone without corroborating evidence of snapping, shedding, or visible short hairs. Brittle from dryness belongs to absorption_blocked, not breakage_active.

buildup_present: Scalp itchiness, dullness, or hair feeling heavy and unresponsive due to layers of old product or sebum. Focuses on the need for a deeper cleanse.
  Example phrases: "scalp is itchy", "hair feels heavy", "product won't wash out", "dull and weighed down", "residue on scalp", "hair looks dirty fast", "gunky", "dull curls and loss of definition", "hair feels oily and greasy", "hair strands take a long time to dry", "curls that don't hold", "tangled hair and brittle ends", "scalp itching", "hair and scalp flakes", "hair and curls are flat and weighed down", "products don't work"

coated_feel: A waxy, plastic-like, or "filmy" texture on the strand, often from silicones or heavy oils, that blocks moisture despite appearing hydrated. Focuses on the tactile feel of the strand and moisture retention failure.
  Example phrases: "waxy feeling", "hair feels coated", "plastic-like texture", "filmy", "silicone buildup", "hair doesn't feel like hair", "greasy but not moisturised", "hair often feels dry even after moisturising", "curls look shiny but feel dry and stiff", "hair doesn't retain moisture", "dry and brittle ends", "loss of volume or movement", "hair feels sticky and waxy", "products no longer work as they used to"

scalp_sensitivity: Scalp is irritated, itchy, tender, flaky, or reactive — due to sensitivity, dryness, or an adverse reaction to a product, NOT from product buildup. Focuses on scalp comfort and barrier health rather than buildup removal.
  Example phrases: "my scalp is itchy", "flaky scalp", "scalp irritation", "scalp is sensitive", "scalp hurts", "tender scalp after styling", "scalp reacts to products", "my child has a sensitive scalp", "scalp dryness", "scalp is inflamed", "scalp burns", "scalp feels sore", "dandruff", "itchy after washing", "scalp feels irritated by my conditioner"

Conversation:
{conversation}"""

_FALLBACK_PROMPT = """\
Role: You are an expert Hair Health Analyst.

The user's message didn't clearly match any standard signal patterns. Your job is to reason about what their description *implies* about their hair or scalp health — even if they never used signal vocabulary.

Ask yourself: what situation is this person describing? What does that situation logically suggest about the state of their hair or scalp?

Signals to reason against:

absorption_blocked: Hair actively repels moisture — products bead up or sit on top rather than absorbing.
  Implied by: explicit product-sitting-on-top behaviour, hair that feels dry immediately after applying heavy moisturisers, interventions consistently failing in a way that suggests a physical barrier. NOT implied by: general dryness from climate, heat, or AC; 4C hair struggling with moisture retention as a hair type trait.

hold_loss: Curls or styles lose shape and definition over time.
  Implied by: styles not lasting through the day, results deteriorating between wash days, curls that start defined but don't stay that way.

breakage_active: Physical damage — snapping, shedding, or thinning strands.
  Implied by: noticing short hairs, hair accumulating in brushes or drains, perceiving hair as thinner or weaker than before.

buildup_present: Scalp or strands blocked by old product or sebum.
  Implied by: scalp discomfort or persistent dryness, hair that looks or feels unclean quickly, products that have stopped performing.

coated_feel: A waxy or filmy layer on the strand blocking moisture.
  Implied by: hair appearing healthy but feeling wrong to the touch, an unexplained texture change, products no longer behaving as expected.

scalp_sensitivity: Scalp is irritated or reactive — not from buildup but from sensitivity or adverse reaction.
  Implied by: scalp discomfort, itching, or flaking after product use; mention of a sensitive or reactive scalp; child or gentle-care context where scalp is the concern; scalp soreness that is not linked to heavy product use.

Only flag a signal if you can reason a clear path from what the user said to what the signal describes. If nothing can be reasonably inferred, set all to false and reflect that in a low confidence score.

User's message:
{conversation}"""

def _all_clear(signals: Dict) -> bool:
    return not any(signals.get(k, False) for k in SIGNAL_NAMES)


async def _run_detection(prompt: str, label: str) -> Dict:
    result = await generate_json(prompt)
    print(f"[SignalDetector][{label}] Raw response: {result}")
    signals = {k: bool(result.get(k, False)) for k in SIGNAL_NAMES}
    signals["confidence_score"] = result.get("confidence_score", 0.0)
    signals["evidence_quote"] = result.get("evidence_quote", "")
    return signals


async def detect_signals(messages: List[Dict[str, str]]) -> Dict[str, bool]:
    conversation = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content') or m.get('message', '')}"
        for m in messages
    )
    print(f"[SignalDetector] Conversation sent:\n{conversation}\n")

    try:
        signals = await _run_detection(_DETECTION_PROMPT.format(conversation=conversation), label="primary")
        signals["fallback_used"] = False

        if _all_clear(signals):
            print("[SignalDetector] All clear — running fallback detection")
            fallback = await _run_detection(_FALLBACK_PROMPT.format(conversation=conversation), label="fallback")
            fallback["fallback_used"] = True
            return fallback

        return signals

    except Exception as e:
        print(f"[SignalDetector] Error: {e}")
        return {k: False for k in SIGNAL_NAMES} | {"confidence_score": 0.0, "evidence_quote": "", "fallback_used": False}
