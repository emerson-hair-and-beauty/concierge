"""Reads a reply and scores it against explicit criteria.

Why this exists
---------------
The three things that can look at a reply see very different amounts:

  tone_rules  exact, free, instant. Catches banned words, hedges, dashes. Cannot
              tell whether a sentence means anything.
  tone_guard  compares vectors. Measured against real text it mostly detects
              "is this long explanatory writing about hair", not "is this
              Emerson" — generic curly-hair copy scored 0.949 while a genuinely
              on-brand short reply scored 0.588.
  this module reads the reply, alongside the instructions the writer was given,
              and answers questions that need comprehension.

The question that matters most is one neither of the others can answer. "Your
curls have great potential, and the key is consistency" contains no banned word,
no hedge, and no dash. It scores respectably on the tone model. It is also empty:
it never says what is wrong with her hair. Only something that reads the sentence
can tell you that.

Judging against the plan, not in a vacuum
-----------------------------------------
The judge is handed the depth, structure, and decision state the writer was told
to follow. "Too long" is meaningless on its own; "asked for 1-3 sentences and
wrote 8" is a fact. This is the main reason it beats a similarity score.

Calibrate it before you trust it
--------------------------------
This is the second judge in this codebase. The first was trained on made-up
examples, was never checked against a human, and turned out to be a coin flip.
Do not repeat that: run scripts/calibrate_judge.py, read the verdicts, and
confirm they match your own reading before using this to gate anything or to
optimise a prompt against.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.services.resilience import record_degraded_call as _record_degraded_call

# Pinned rather than following LLM_PROVIDER on purpose. If the judge changes
# model, scores stop being comparable across runs, and every before/after
# measurement built on it silently becomes meaningless.
JUDGE_MODEL = os.getenv("TONE_JUDGE_MODEL", "gpt-5")

_CONSEQUENCE = (
    "Scoring is an offline quality check, not part of answering a customer.\n"
    "  Replies are unaffected; you just lose the measurement."
)


def _record(source: str, detail: str, error: Exception) -> None:
    _record_degraded_call(source, detail, error, subsystem="Tone judge", consequence=_CONSEQUENCE)


# Each criterion is a question with a stated failure mode. The failure modes are
# taken from failures actually observed in this pipeline, not invented: the vague
# reply, the parroted internal note, the eight-sentence answer to a "1-3
# sentences" instruction.
CRITERIA: dict[str, dict[str, str]] = {
    "names_cause": {
        "question": "Does it name a specific, concrete cause for what this person described?",
        "fails_when": (
            "It gestures at a cause without naming one, or substitutes encouragement for "
            "diagnosis. 'Your curls have great potential and the key is consistency' scores 1: "
            "it never says what is wrong. 'Mineral film from hard water is coating the strand "
            "and blocking absorption' scores 5."
        ),
    },
    "follows_depth": {
        "question": "Does the length match the depth instruction it was given?",
        "fails_when": (
            "It overshoots or undershoots the stated range. Judge against the instruction you "
            "are shown, not against your own taste. Eight sentences where 1-3 were asked for "
            "scores 1, however good the writing is."
        ),
    },
    "follows_structure": {
        "question": "Does it hit the beats of the structure it was told to follow?",
        "fails_when": (
            "It skips beats or invents its own order. If a beat is impossible to satisfy "
            "honestly, say so in the reason: that is a fault in the instruction, not the reply."
        ),
    },
    "answers_them": {
        "question": "Does it respond to what this person actually said, in their situation?",
        "fails_when": (
            "It answers a generic version of the question, recites the diagnosis, or ignores "
            "what they told you. Using their own details back is good; parroting internal "
            "system wording is not."
        ),
    },
    "sounds_emerson": {
        "question": "Could this only have come from Emerson?",
        "fails_when": (
            "It would fit any beauty brand's website, or drifts into social-media hype, "
            "support-ticket formality, or catalogue listing. Emerson writes with authority, "
            "takes positions, uses curl-community terms freely, and defines science terms in "
            "plain English on first use."
        ),
    },
    "stays_grounded": {
        "question": "Does it stay inside what the products and context actually support?",
        "fails_when": (
            "It invents mechanisms, promises growth or permanence, or makes health claims. "
            "This one is a safety check: score it strictly."
        ),
    },
}

_SYSTEM = """You are a strict editor reviewing replies written by a curly-hair concierge for \
Emerson, a curl brand serving the UAE and GCC.

Score each criterion from 1 to 5:
  1 clear failure   2 weak   3 acceptable   4 good   5 exemplary

Rules:
- Judge only against the instructions you are shown. Do not invent requirements.
- Quote the exact words that drove your score. A reason without evidence is not a reason.
- Be strict. A reply that reads pleasantly while saying nothing specific is a failure, not a 3.
- If an instruction is impossible to satisfy honestly, say so in the reason and do not punish \
the reply for it.

Return only JSON:
{"scores": {"<criterion>": {"score": <1-5>, "reason": "<one sentence, quoting evidence>"}}, \
"worst_problem": "<the single most important thing to fix, or empty if none>"}"""


def _build_prompt(reply: str, plan: dict[str, Any]) -> str:
    criteria = "\n".join(
        f"- {name}: {c['question']}\n    Fails when: {c['fails_when']}"
        for name, c in CRITERIA.items()
    )
    instructions = "\n".join(f"{k}: {v}" for k, v in plan.items() if v)
    return (
        f"THE WRITER WAS TOLD:\n{instructions}\n\n"
        f"CRITERIA:\n{criteria}\n\n"
        f"THE REPLY:\n{reply.strip()}"
    )


def judge(reply: str, plan: dict[str, Any] | None = None, model: str | None = None) -> dict | None:
    """Score one reply. Returns None if the judge could not run.

    `plan` carries what the writer was asked to do — depth, structure, decision
    state, and the customer's message. Without it, criteria like follows_depth
    have nothing to check against and the judge falls back to taste.

    Costs one call to a strong model. This is for offline evaluation; it is not
    on the path of answering a customer.
    """
    if not reply.strip():
        return None

    try:
        from openai import OpenAI

        from app.config import OPENAI_API_KEY

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model or JUDGE_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _build_prompt(reply, plan or {})},
            ],
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content)
    except Exception as e:
        _record("tone_judge.judge", "no judge verdict for this reply", e)
        return None

    scores = parsed.get("scores", {})
    values = [
        s["score"] for s in scores.values() if isinstance(s, dict) and isinstance(s.get("score"), (int, float))
    ]
    if not values:
        return None

    return {
        "scores": scores,
        "worst_problem": parsed.get("worst_problem", ""),
        # Reported together on purpose. The average is what an optimiser can
        # follow; the minimum is what tells you something is actually broken,
        # because five good criteria will happily hide one score of 1.
        "average": round(sum(values) / len(values), 2),
        "lowest": min(values),
    }


def plan_from_composer_input(composer_input, user_message: str | None = None) -> dict[str, Any]:
    """Pull the instructions the writer was given out of a ResponseComposerInput."""
    from app.services.decision_state.response_composer import (
        _DEPTH_INSTRUCTIONS,
        _resolve_structure,
    )

    plan = composer_input.jte_delivery_plan
    messages = composer_input.recent_messages or []
    latest = user_message or (messages[-1].get("content") if messages else "")

    return {
        "customer said": latest,
        "decision state": composer_input.strategy_payload.decision_state,
        "tone": plan.tone_profile,
        "required length": _DEPTH_INSTRUCTIONS.get(plan.response_depth, plan.response_depth),
        # Must go through _resolve_structure, not the four-beat table directly.
        # At `short` the writer is given a two-beat structure; judging against the
        # four-beat one marked correct replies as structure failures.
        "required structure": _resolve_structure(plan),
    }
