"""Find rules in the composer prompt that give orders about the same thing.

The bug this catches
--------------------
Every block in response_composer.py is sensible read on its own. The damage only
appears in the combination, and there is no single file you can review to see it.

Measured before this script existed, a reply to one frustrated customer arrived
with four separate instructions about how to open:

  voice block   "Open by addressing what the customer already believes"
  task footer   "If they expressed frustration, name it directly before advice"
  tone profile  "Lead with empathy. Name what the user is feeling first"
  depth rule    "fold the acknowledgement into the first sentence"

Plus a structure whose first beat was "What is Working". Five first moves, all
arriving at once, none aware of the others. The model cannot obey five openings,
so it does a little of each, which is exactly what a stock phrase is. Every reply
began "I hear your frustration" until these were reduced to one owner.

It also gets worse over time, because the natural fix for "it keeps hedging" is
to add the rule again somewhere else. The resolution rule ended up stated in the
voice block and repeated in all four tone profiles.

How to read the output
----------------------
Only ONE option is used per reply from each table: one tone, one depth, one
structure. So the number that matters is the per-reply count, not how many times
a phrase appears across the whole file. This reports the worst case across every
combination.

One owner per concern is the goal. Two is usually a smell. Three or more means
the model is being asked to satisfy instructions that cannot all be satisfied,
and it will produce a formula that half-satisfies each.

Sections are discovered automatically, so renaming or adding blocks in the
composer will not silently stop this from checking them.

Usage:
    python scripts/audit_prompt_rules.py
    python scripts/audit_prompt_rules.py --max-owners 1 --verbose
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.decision_state import response_composer as rc  # noqa: E402

# What counts as "giving orders about" a concern. Patterns, not exact words, so a
# rewording does not slip past. Add to this when a new kind of clash bites you.
CONCERNS: dict[str, str] = {
    "how to open": r"open(?!ly)\b|lead with|first sentence|before (?:giving|moving)|start(?:s|ing)? (?:by|with)|preamble",
    "how long": r"\bsentence|length|brief\b|concise|nothing else|complete every|short\b",
    "hedging": r"qualifier|unresolved|hedge|assertion|possibilit|vague",
    # Deliberately narrow. An earlier version matched bare "seen", which fired on
    # "you have seen this pattern many times" — an instruction about confidence,
    # not about empathy. A checker that cries wolf gets ignored.
    "empathy": r"empath|feel seen|how they feel|what .{0,20}feeling|acknowledge (?:how|their|the)",
    "products": r"\bproduct|purchase|\bbuy\b|recommend",
    "jargon": r"jargon|plain english|define .{0,20}term|curl community",
}

# Overlaps that are correct by design. Each needs a reason, so that "we decided
# this is fine" never gets confused with "nobody has looked at this yet".
ALLOWED: dict[str, str] = {
    "products": (
        "cta_instructions sets purchase pressure and exposure_instructions sets whether a "
        "product may be named at all. Two dimensions of one topic, not two answers to one "
        "question. The remaining mentions are context (what Emerson sells) rather than orders."
    ),
}

# Blocks shorter than this are labels or separators, not instructions.
_MIN_BLOCK = 40


def discover() -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Split the composer's module constants into always-on blocks and option tables.

    A dict of strings is a table where exactly one entry is chosen per reply
    (tone, depth, structure). A long string constant is a block that is always
    present. Discovered by inspection so this keeps working as the file changes.
    """
    blocks: dict[str, str] = {}
    tables: dict[str, dict[str, str]] = {}

    for name in dir(rc):
        if not name.startswith("_") or name.startswith("__"):
            continue
        value = getattr(rc, name)
        if isinstance(value, str) and len(value) >= _MIN_BLOCK:
            blocks[name.strip("_").lower()] = value
        elif isinstance(value, dict) and value and all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            tables[name.strip("_").lower()] = value

    # Drop assembled templates. Anything with {placeholders} is the frame the
    # rules get poured into, not a rule itself, and templates are alternatives to
    # each other rather than things that appear together in one reply. Detected by
    # shape rather than by name so new templates are excluded automatically.
    for name in [n for n, t in blocks.items() if re.search(r"\{[a-z_]+\}", t)]:
        blocks.pop(name)
    return blocks, tables


def owners(text_by_section: dict[str, str], pattern: str) -> list[str]:
    return [n for n, t in text_by_section.items() if re.search(pattern, t, re.I)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Find clashing rules in the composer prompt.")
    parser.add_argument("--max-owners", type=int, default=2,
                        help="Fail if any concern has more than this many owners in one reply (default 2).")
    parser.add_argument("--verbose", action="store_true", help="Show every section, including clean ones.")
    args = parser.parse_args()

    blocks, tables = discover()

    print(f"\nFound {len(blocks)} always-on blocks and {len(tables)} option tables in response_composer.")
    if args.verbose:
        print("  blocks: " + ", ".join(sorted(blocks)))
        for name, table in sorted(tables.items()):
            print(f"  table {name}: {len(table)} options")

    combos = list(itertools.product(*([(n, k) for k in t] for n, t in tables.items()))) if tables else [()]
    print(f"Checking {len(combos)} possible reply configurations.\n")

    failures = []
    for concern, pattern in CONCERNS.items():
        block_owners = owners(blocks, pattern)

        worst_count, worst_owners = len(block_owners), list(block_owners)
        for combo in combos:
            active = dict(blocks)
            for table_name, key in combo:
                active[f"{table_name}:{key}"] = tables[table_name][key]
            found = owners(active, pattern)
            if len(found) > worst_count:
                worst_count, worst_owners = len(found), found

        allowed = concern in ALLOWED
        ok = worst_count <= args.max_owners or allowed
        if not ok:
            failures.append(concern)
        if ok and not args.verbose and worst_count <= 1:
            continue

        label = "ALLOW" if allowed and worst_count > args.max_owners else ("OK  " if ok else "CLASH")
        print(f"[{label}] {concern:14s} {worst_count} owner(s) in a single reply")
        for o in worst_owners:
            print(f"           {o}")
        if allowed and worst_count > args.max_owners:
            print(f"           reason: {ALLOWED[concern]}")
        print()

    if failures:
        print(
            f"{len(failures)} concern(s) with more than {args.max_owners} owners: "
            + ", ".join(failures)
            + "\n\nGive each one a single owner and delete the duplicates. Repeating a rule does\n"
            "not make it more likely to be followed; it makes the model average the versions\n"
            "together, which is how a stock phrase is born.\n"
        )
        return 1

    print("No concern has more than "
          f"{args.max_owners} owners in any single reply.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
