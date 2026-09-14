"""Signal detection by reading the conversation, with no example phrases.

Same shape as app/services/session_signal/signal_detector.py: one prompt string,
one runner, one entry point. The difference is the prompt, which gives each
signal a meaning and an edge instead of a list of phrases to match.
"""

from typing import List, Dict

from app.agents.llm_call.provider import generate_json
from app.services.session_signal.signal_detector import SIGNAL_NAMES

_JUDGE_PROMPT = """\
Role: You are an expert Hair Health Analyst reading a support conversation for a curl brand.

Detection Instructions:
Decide, for each signal, whether the CUSTOMER's own description matches what the signal means.
Judge by meaning, not by words. A customer can use a signal's vocabulary without having that
problem, and can have the problem without ever using the vocabulary.

Rules:
- Quote the CUSTOMER only. If only the assistant said it, the signal is false. The assistant
  recommends products and repeats the problem back; that is not evidence.
- A problem the customer says is solved, or says is not happening, is false.
- Be strict. If the description is ambiguous, mark it false and say so in the reason.
- Every signal you mark true needs a quote. No quote means false.

Signal Definitions:

absorption_blocked: Hair repels moisture. Product sits on the surface instead of going in.
  True when: the customer says product sits on top, beads up, or that repeated attempts to
  moisturise fail in a way that points to a physical barrier.
  False when: dryness the customer blames on climate, heat, or air conditioning. Ordinary
  dryness with no account of products failing.

hold_loss: The curl loses its SHAPE, DEFINITION, VOLUME, or HOLD as time passes.
  True when: the style degrades. Curls drop, definition goes, the shape does not last.
  False when: the style lasted and has only a local flaw, such as frizz in one area. Something
  other than the curl shape gets worse, such as dryness or scalp pain. A day count on its own
  decides nothing: ask what got worse.

breakage_active: Strands physically break, shed, or thin.
  True when: snapping, short broken pieces, hair in the brush or drain, or a loss of density.
  False when: the word brittle on its own, with nothing that says the hair is breaking.

buildup_present: Old product or sebum sits on the scalp or strand and needs a deeper cleanse.
  True when: the customer names residue, flaking together with buildup, heaviness, or hair
  that feels unclean quickly.
  False when: an itchy or sore scalp with no sign of residue or heaviness. That is
  scalp_sensitivity, not this.

coated_feel: A waxy or filmy layer on the strand blocks moisture.
  True when: the customer describes how the strand FEELS: waxy, plastic, filmy, coated.
  False when: dryness or dullness with no complaint about how the strand feels to touch.

scalp_sensitivity: The scalp is irritated, sore, itchy, flaky, or reactive, and not from buildup.
  True when: the customer describes scalp discomfort, pain, inflammation, or a reaction to a product.
  False when: the discomfort is clearly tied to heavy product residue. That is buildup_present,
  not this.

Return only JSON, with all six signals present:
{{"<signal name>": {{"present": true or false, "quote": "<the customer's exact words, or empty>", \
"reason": "<one sentence>"}}}}

Conversation:
{conversation}"""


def _empty() -> Dict:
    return {k: False for k in SIGNAL_NAMES} | {"evidence": {}, "reasons": {}}


def _coerce(result: Dict) -> Dict:
    """Read the response into signals, quotes, and reasons.

    A signal marked present with no quote becomes false. The prompt says the same
    thing, and the model breaks it often enough that the code enforces it too.
    """
    signals: Dict[str, bool] = {}
    evidence: Dict[str, str] = {}
    reasons: Dict[str, str] = {}

    for name in SIGNAL_NAMES:
        entry = result.get(name)
        if not isinstance(entry, dict):
            signals[name] = False
            continue
        quote = str(entry.get("quote") or "").strip()
        signals[name] = bool(entry.get("present")) and bool(quote)
        if signals[name]:
            evidence[name] = quote
        reason = str(entry.get("reason") or "").strip()
        if reason:
            reasons[name] = reason

    return signals | {"evidence": evidence, "reasons": reasons}


async def judge(messages: List[Dict[str, str]]) -> Dict:
    conversation = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content') or m.get('message', '')}"
        for m in messages
    )
    print(f"[SignalJudge] Conversation sent:\n{conversation}\n")

    if not conversation.strip():
        return _empty()

    try:
        result = await generate_json(_JUDGE_PROMPT.format(conversation=conversation))
        print(f"[SignalJudge] Raw response: {result}")
        if not isinstance(result, dict):
            return _empty()
        return _coerce(result)
    except Exception as e:
        print(f"[SignalJudge] Error: {e}")
        return _empty()
