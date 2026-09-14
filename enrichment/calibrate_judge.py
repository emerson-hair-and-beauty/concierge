"""Check the signal judge against cases where the answer is not in doubt.

tone_judge.py records why this exists. The first judge in this codebase was built
from made-up examples, was never checked against a person, and scored a coin flip
on unseen text. Nothing caught it for weeks, because a judge nobody audits always
looks fine.

So this one gets audited before it writes to anybody's profile.

Most cases below are Kety's real words, taken from _chat.txt while debugging the
phrase-list detector. Those are the ones we now know the answer to:

  "my wash and go lasts a week ... frizz at the back top"   NOT hold_loss
  "by day 3 or 4 it is so dry and painful"                  NOT hold_loss
  "it only the front where it get inflammed"                IS  scalp_sensitivity

The old detector got the first two wrong, twice, after two prompt patches.

Usage:
    python -m enrichment.calibrate_judge
    python -m enrichment.calibrate_judge --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from enrichment import signal_judge  # noqa: E402

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def u(text: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": text}]


# (name, signal under test, PRESENT or ABSENT, messages)
CASES = [
    (
        "Kety: the style lasted, frizz in one area",
        "hold_loss", "ABSENT",
        u("Usually my wash and go lasts a week , the curls lasts even tho I do have an "
          "issue with frizz at the back top of my hair. The hair itself feels soft."),
    ),
    (
        "Kety: a day count, but dryness is what got worse",
        "hold_loss", "ABSENT",
        u("By day 3 or 4 it's so dry and painful"),
    ),
    (
        "Kety: flaking together with buildup",
        "buildup_present", "PRESENT",
        u("mainly around my temples in the front it does get flaky and there's more buildup"),
    ),
    (
        "Kety: inflamed and sore scalp",
        "scalp_sensitivity", "PRESENT",
        u("it only the front where it get inflammed and then eventually hurts like a bruise"),
    ),
    (
        "only the agent uses hold vocabulary",
        "hold_loss", "ABSENT",
        [
            {"role": "user", "content": "hi, what do you recommend for my hair?"},
            {"role": "assistant", "content": "For great definition and hold that lasts all week, "
                                             "we recommend letting your curls naturally clump."},
            {"role": "user", "content": "ok thanks, I'll try that"},
        ],
    ),
    (
        "a real hold loss",
        "hold_loss", "PRESENT",
        u("my curls drop flat by noon and the definition is gone, styles just don't last"),
    ),
    (
        "itchy scalp with no residue is not buildup",
        "buildup_present", "ABSENT",
        u("my scalp is really itchy and sore lately, it stings after I wash"),
    ),
    (
        "itchy scalp with no residue is sensitivity",
        "scalp_sensitivity", "PRESENT",
        u("my scalp is really itchy and sore lately, it stings after I wash"),
    ),
    (
        "dryness blamed on the air conditioning",
        "absorption_blocked", "ABSENT",
        u("my hair gets dry but honestly it's the office air conditioning, it's brutal"),
    ),
    (
        "products sit on top and nothing works",
        "absorption_blocked", "PRESENT",
        u("I've tried every leave-in and cream, they all just sit on top and my hair stays dry"),
    ),
    (
        "snapping with short pieces",
        "breakage_active", "PRESENT",
        u("my hair keeps snapping when I detangle, there are loads of short broken pieces"),
    ),
    (
        "brittle alone is not breakage",
        "breakage_active", "ABSENT",
        u("my ends feel a bit brittle"),
    ),
    (
        "a tactile complaint about coating",
        "coated_feel", "PRESENT",
        u("my hair feels waxy and almost plastic even right after washing it"),
    ),
    (
        "a problem the customer says is solved",
        "breakage_active", "ABSENT",
        u("I used to have loads of breakage but that stopped completely after I changed brush"),
    ),
]


async def run() -> list[tuple]:
    results = await asyncio.gather(*(signal_judge.judge(m) for _, _, _, m in CASES))
    await asyncio.sleep(0.25)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the signal judge against known cases.")
    parser.add_argument("--verbose", action="store_true",
                        help="Print every signal the judge returned, not just the one under test.")
    args = parser.parse_args()

    print(f"\nAuditing the signal judge against {len(CASES)} cases where the answer is clear.")
    print("A case passes when the judge agrees with a careful reader.\n")

    verdicts = asyncio.run(run())
    agreed = 0
    failures = []

    for (name, signal, expected, _), result in zip(CASES, verdicts):
        got = "PRESENT" if result.get(signal) else "ABSENT"
        ok = got == expected
        agreed += ok
        if not ok:
            failures.append(name)

        print(f"  [{'OK  ' if ok else 'MISS'}] {signal:20s} want {expected:7s} got {got:7s}  {name}")
        reason = result.get("reasons", {}).get(signal, "")
        quote = result.get("evidence", {}).get(signal, "")
        if quote:
            print(f'         quote:  "{quote[:110]}"')
        if reason:
            print(f"         reason: {reason[:110]}")
        if args.verbose:
            others = [k for k in signal_judge.SIGNAL_NAMES if k != signal and result.get(k)]
            print(f"         also present: {', '.join(others) or '-'}")
        print()

    print(f"Agreement: {agreed}/{len(CASES)}")
    if failures:
        print("Disagreed on: " + ", ".join(failures))
    print()

    if agreed == len(CASES):
        print("The judge agrees on every clear case, including the three the phrase-list\n"
              "detector got wrong. Safe to measure with. Run it against 20 real chats next.\n")
        return 0
    if agreed >= len(CASES) - 1:
        print("Close. Read the miss above before you build on this. One blind spot is worth\n"
              "understanding, because it will not stay in one place.\n")
        return 1
    print("Do not use this yet. It disagrees with cases a careful reader would not,\n"
          "which is exactly how the previous judge went unnoticed as a coin flip.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
