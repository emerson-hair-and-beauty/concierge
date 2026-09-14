"""Check the judge against cases where we already know the answer.

The first judge in this codebase (the Simasia tone model) was built from made-up
examples, never checked against a person, and turned out to score 0.543 on unseen
text: a coin flip. Nothing caught it for weeks because a judge that is never
audited always looks fine.

So this one gets audited first. Every case below is a reply whose verdict is not
in doubt, paired with the criterion it should expose and the direction the score
must go. If the judge disagrees with an obvious case, it is not ready to gate
anything, and it is certainly not ready to have a prompt optimised against it.

Most cases are real output from this pipeline, captured earlier while debugging.

Usage:
    python scripts/calibrate_judge.py
    python scripts/calibrate_judge.py --model gpt-5-mini    # cheaper judge
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services import tone_judge  # noqa: E402

SHORT = "1-3 sentences. One decision, one next step. Nothing else."
MEDIUM = "3-5 sentences. One brief explanation of why, then the action."
TROUBLESHOOT = "What is Happening > Most Likely Cause > What to Change First > What to Monitor."

# (name, criterion under test, expected LOW or HIGH, reply, plan)
CASES = [
    (
        "vague: comfort instead of diagnosis",
        "names_cause",
        "LOW",
        "I hear the frustration in your words, and it's completely understandable. When it feels "
        "like nothing is working, it can be exhausting. Let's focus on one thing that could make a "
        "difference without overwhelming you further: consistency. Stick with a simple regimen for "
        "a few weeks. You're not alone in this, and patience will reveal what your curls truly need.",
        {"customer said": "ive tried everything and nothing works", "required length": SHORT},
    ),
    (
        "specific: names the mechanism",
        "names_cause",
        "HIGH",
        "Day 3 curls falling flat comes down to buildup, not moisture. Your leave-in is sitting on "
        "the cuticle instead of absorbing. Clarify once this week, then reintroduce it on damp hair.",
        {"customer said": "my day 3 curls have gone flat", "required length": SHORT},
    ),
    (
        "eight sentences where three were asked for",
        "follows_depth",
        "LOW",
        "I hear you, and it's completely understandable to feel overwhelmed when nothing seems to be "
        "working. Let's simplify things together. You've got fantastic curls with great potential. "
        "The challenge here isn't about needing more products or a drastic cut. It's about finding a "
        "routine that respects your hair's high porosity and its reaction to humidity. Focus on one "
        "simple change: try sealing your hair with an oil or cream post-styling to lock in moisture "
        "and combat frizz. Consistency is key in this kind of climate; stick with this step for a few "
        "weeks to see meaningful results. You're not alone in this, and your curls are worth the journey.",
        {"customer said": "nothing works, im ready to cut it off", "required length": SHORT},
    ),
    (
        "correct length for the instruction",
        "follows_depth",
        "HIGH",
        "That squeaky feeling after washing means the cuticle has been stripped bare. Follow with a "
        "leave-in while the hair is still wet.",
        {"customer said": "my hair squeaks after washing", "required length": SHORT},
    ),
    (
        "social media hype",
        "sounds_emerson",
        "LOW",
        "Babe, this leave-in is my absolute holy grail and I am obsessed. Your curls are going to "
        "look so amazing after one wash day, honestly a total game changer, you will love it.",
        {"customer said": "what leave-in should I use?", "required length": MEDIUM},
    ),
    (
        "support-ticket formality",
        "sounds_emerson",
        "LOW",
        "Kindly be advised that your hair care inquiry has been received and is currently being "
        "processed. A member of our team will review your curl concerns and revert to you in due course.",
        {"customer said": "my curls are so dry lately", "required length": MEDIUM},
    ),
    (
        "invented science and growth claims",
        "stays_grounded",
        "LOW",
        "This serum penetrates deep into the follicle to reactivate dormant growth cells at the root. "
        "Clinical-grade peptides rebuild damaged bonds permanently and stimulate new hair production "
        "within weeks, reversing years of thinning.",
        {"customer said": "my hair feels thinner than it used to", "required length": MEDIUM},
    ),
    (
        "ignores what she said, recites the diagnosis",
        "answers_them",
        "LOW",
        "Buildup or a waxy coating is blocking absorption. A clarifying reset must happen before any "
        "routine will be effective. The decision state here is reset first, so the slate needs to be "
        "clean before anything else is recommended.",
        {
            "customer said": "im going to a wedding saturday and my hair looks awful, help",
            "required length": MEDIUM,
        },
    ),
    (
        "follows every beat of the structure",
        "follows_structure",
        "HIGH",
        "Your definition is disappearing by midday because Dubai's humidity swells the cuticle and "
        "lifts the curl pattern apart. The cause is a humectant-heavy styler pulling moisture from "
        "the air straight into the strand. Switch to a glycerin-free gel and seal over it with a light "
        "occlusive. Watch whether your cast holds past lunchtime this week.",
        {
            "customer said": "my definition is gone by lunchtime here in dubai",
            "required length": MEDIUM,
            "required structure": TROUBLESHOOT,
        },
    ),
    (
        "skips most of the structure",
        "follows_structure",
        "LOW",
        "Humidity is rough on curls in Dubai. Try a different gel and see how you get on.",
        {
            "customer said": "my definition is gone by lunchtime here in dubai",
            "required length": MEDIUM,
            "required structure": TROUBLESHOOT,
        },
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the judge against known cases.")
    parser.add_argument("--model", default=None, help=f"Override the judge model (default {tone_judge.JUDGE_MODEL}).")
    parser.add_argument("--verbose", action="store_true", help="Print every criterion, not just the one under test.")
    args = parser.parse_args()

    print(f"\nAuditing judge ({args.model or tone_judge.JUDGE_MODEL}) against {len(CASES)} known cases.")
    print("A case passes when the score moves the way an editor would expect.\n")

    agreed = 0
    failures = []

    for name, criterion, expected, reply, plan in CASES:
        verdict = tone_judge.judge(reply, plan, model=args.model)
        if verdict is None:
            print(f"  [ERROR] {name}: judge did not return a verdict")
            failures.append(name)
            continue

        entry = verdict["scores"].get(criterion, {})
        score = entry.get("score")
        if score is None:
            print(f"  [ERROR] {name}: judge did not score {criterion}")
            failures.append(name)
            continue

        # Deliberately generous bands. We are asking whether it can tell obvious
        # good from obvious bad, not whether it agrees on the exact number.
        ok = score <= 2 if expected == "LOW" else score >= 4
        agreed += ok
        if not ok:
            failures.append(name)

        print(f"  [{'OK  ' if ok else 'MISS'}] {criterion:18s} want {expected:4s} got {score}   {name}")
        print(f"         {entry.get('reason', '')[:150]}")
        if args.verbose:
            for other, s in verdict["scores"].items():
                if other != criterion:
                    print(f"           {other:18s} {s.get('score')}  {s.get('reason','')[:90]}")
        print()

    print(f"Agreement: {agreed}/{len(CASES)}")
    if failures:
        print("Disagreed on: " + ", ".join(failures))
    print()
    if agreed == len(CASES):
        print("The judge tracks an editor's reading on every obvious case. Safe to measure with,\n"
              "and safe to optimise a prompt against.\n")
        return 0
    if agreed >= len(CASES) - 1:
        print("Close, but read the miss above. One blind spot is worth understanding before you\n"
              "build on this, because an optimiser will find and exploit it.\n")
        return 1
    print("Do not build on this yet. It disagrees with obvious cases, which is exactly how the\n"
          "previous tone model went unnoticed as a coin flip.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
