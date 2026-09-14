"""Compare three ways of detecting signals in a real WhatsApp conversation.

Why this exists
---------------
Two questions block the enrichment design, and neither can be answered by
reasoning about it:

1. Does the agent's own voice create false signals? The detector was tuned on the
   chat pipeline, where the assistant is our own composer. On WhatsApp the
   assistant is a person, and people restate the problem back to the customer:
   "so the breakage started after you changed shampoo?". Nothing in the detection
   prompt says a signal must come from the customer.

2. Does one pass over a transcript find what per-message detection finds? One
   pass sees links that a ten-message window cannot. A ten-message window gives
   each message its own undivided call. Neither is strictly safer.

So this runs all three and prints the difference. The number that matters most is
"both sides found it, customer only did not" — that is question 1, measured.

Getting the input
-----------------
The number is not on the Cloud API, so there is no webhook. Ask the agent to open
each chat in the WhatsApp Business app, choose "Export chat", then "Without
media". Put the files in data/whatsapp_exports/.

Usage:
    python -m enrichment.compare --dry-run          # parse only, no model calls
    python -m enrichment.compare                    # all three modes
    python -m enrichment.compare --limit 5          # try it on five first
    python -m enrichment.compare --skip-per-message # the two cheap modes only
    python -m enrichment.compare --agent "Emerson Support"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from enrichment import contacts, parse_export  # noqa: E402
from enrichment.detect import active, detect_once, detect_per_message, quiet  # noqa: E402

# The default Windows loop raises "Event loop is closed" while httpx tears down
# connections nothing ever closed. The selector loop shuts down quietly.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DEFAULT_DIR = PROJECT_ROOT / "data" / "whatsapp_exports"

# Below this the model is guessing at the name, and a wrong name reaches a real
# customer. Treat anything under it as no name found.
NAME_FLOOR = 0.7


def _fmt(signals: set[str]) -> str:
    return ", ".join(sorted(signals)) if signals else "-"


async def run_one(turns: list[dict[str, str]], skip_per_message: bool) -> dict:
    only_customer = parse_export.customer_only(turns)

    customer_pass, both_pass, name = await asyncio.gather(
        detect_once(only_customer),
        detect_once(turns),
        contacts.find_name(turns),
    )

    per_message = None
    if not skip_per_message:
        per_message = await detect_per_message(turns)

    return {
        "customer_only": active(customer_pass),
        "both_sides": active(both_pass),
        "per_message": active(per_message) if per_message else None,
        "by_layer": both_pass.get("by_layer", {}),
        "calls_per_message": (per_message or {}).get("calls", 0),
        "email": contacts.pick_email(turns),
        "obfuscated": contacts.count_obfuscated(turns),
        "name": name,
        "truncated": both_pass.get("truncated", False),
    }


async def run_all(exports: dict, agent: str | None, skip_per_message: bool) -> dict:
    """Detect over every export inside one event loop.

    One loop for the whole run, not one for each file. The provider builds a new
    HTTP client per call and never closes it, so a loop that closes underneath an
    open client raises "Event loop is closed" and buries the report in tracebacks.

    Progress goes to stderr because `quiet` redirects stdout for the whole run.
    """
    results: dict[Path, dict] = {}
    with quiet():
        for i, (path, turns) in enumerate(exports.items(), 1):
            print(f"  [{i}/{len(exports)}] {path.name}", file=sys.stderr, flush=True)
            mapped = parse_export.to_turns(turns, agent)
            results[path] = await run_one(mapped, skip_per_message)
    # Give the unclosed HTTP clients a moment to shut down before the loop does.
    await asyncio.sleep(0.25)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage:")[0].strip())
    parser.add_argument("target", nargs="?", default=str(DEFAULT_DIR),
                        help=f"Export file or directory (default {DEFAULT_DIR}).")
    parser.add_argument("--agent", default=None,
                        help="The agent's name as it appears in the export. Inferred when omitted.")
    parser.add_argument("--limit", type=int, default=None, help="Read only the first N files.")
    parser.add_argument("--skip-per-message", action="store_true",
                        help="Skip the per-message mode. It costs one call for every customer turn.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse the exports and stop. Makes no model calls and needs no API key.")
    args = parser.parse_args()

    target = Path(args.target)
    paths = parse_export.find_exports(target)
    if not paths:
        print(f"\nNo .txt exports found at {target}.")
        print("Ask the agent to export each chat from the WhatsApp Business app:")
        print("  open the chat > menu > Export chat > Without media\n")
        return 1
    if args.limit:
        paths = paths[: args.limit]

    exports = {p: parse_export.read_export(p) for p in paths}
    exports = {p: t for p, t in exports.items() if t}
    if not exports:
        print(f"\nParsed {len(paths)} files and found no messages in any of them.")
        print("The export format may differ. Run with --dry-run and check one file by hand.\n")
        return 1

    agent = args.agent or parse_export.infer_agent(exports)
    print(f"\nRead {len(exports)} exports from {target}")
    if agent:
        seen = sum(1 for t in exports.values() if any(x.sender == agent for x in t))
        how = "given" if args.agent else "inferred"
        print(f"Agent {how} as {agent!r} (appears in {seen} of {len(exports)} files)")
    else:
        print("Agent NOT identified. Every turn counts as the customer, which overstates")
        print("what the customer said and makes the comparison meaningless.")
        print("Pass --agent \"Their Name\" using the name as it appears in the export.")
        if not args.dry_run:
            return 1

    print()
    for path, turns in exports.items():
        senders = Counter(t.sender for t in turns)
        agent_turns = senders.get(agent, 0) if agent else 0
        print(f"  {path.name:32s} {len(turns):4d} turns  "
              f"({len(turns) - agent_turns} customer, {agent_turns} agent)")

    if args.dry_run:
        print(f"\nParsed {sum(len(t) for t in exports.values())} turns. No model calls made.")
        print("Check a few against the original chats, then run again without --dry-run.\n")
        return 0

    cheap = len(exports) * 5  # two forced passes (2 calls each) plus one name call
    print(f"\nEstimated calls: {cheap} for the one-pass modes and the names.")
    if not args.skip_per_message:
        turns_total = sum(sum(1 for t in v if t) for v in exports.values())
        print(f"Plus roughly {turns_total} more for per-message mode. Use --skip-per-message to drop it.")
    print()

    results = asyncio.run(run_all(exports, agent, args.skip_per_message))

    for i, (path, result) in enumerate(results.items(), 1):
        print(f"[{i}/{len(results)}] {path.name}")
        print(f"  customer only   {_fmt(result['customer_only'])}")
        print(f"  both sides      {_fmt(result['both_sides'])}")
        if result["per_message"] is not None:
            print(f"  per message     {_fmt(result['per_message'])}")

        added = result["both_sides"] - result["customer_only"]
        if added:
            print(f"  ! both sides added {_fmt(added)} - check whether the agent said it")
        if result["truncated"]:
            print("  ! transcript longer than the cap, the oldest messages were dropped")
        print()

    # ---- summary -------------------------------------------------------
    print("=" * 68)
    print("SUMMARY")
    print("=" * 68)

    totals = {mode: 0 for mode in ("customer_only", "both_sides", "per_message")}
    agent_added: Counter[str] = Counter()
    window_only: Counter[str] = Counter()
    one_pass_only: Counter[str] = Counter()

    for result in results.values():
        totals["customer_only"] += len(result["customer_only"])
        totals["both_sides"] += len(result["both_sides"])
        agent_added.update(result["both_sides"] - result["customer_only"])
        if result["per_message"] is not None:
            totals["per_message"] += len(result["per_message"])
            window_only.update(result["per_message"] - result["both_sides"])
            one_pass_only.update(result["both_sides"] - result["per_message"])

    print("\n  Signals found, by mode")
    print(f"    customer only   {totals['customer_only']}")
    print(f"    both sides      {totals['both_sides']}")
    if not args.skip_per_message:
        print(f"    per message     {totals['per_message']}")

    added_total = sum(agent_added.values())
    print(f"\n  Both sides found, customer only did not:  {added_total}")
    print("    This is question 1. A high number means the agent's words create signals.")
    for name, count in agent_added.most_common():
        print(f"      {name:22s} {count}")

    if not args.skip_per_message:
        print(f"\n  Per message found, one pass did not:  {sum(window_only.values())}")
        print("    One pass missed these. Small mentions lost in a long transcript.")
        for name, count in window_only.most_common():
            print(f"      {name:22s} {count}")
        print(f"\n  One pass found, per message did not:  {sum(one_pass_only.values())}")
        print("    The ten-message window missed these. Links across distant messages.")
        for name, count in one_pass_only.most_common():
            print(f"      {name:22s} {count}")

    with_email = sum(1 for r in results.values() if r["email"])
    obfuscated = sum(r["obfuscated"] for r in results.values())
    with_name = sum(1 for r in results.values()
                    if r["name"]["name"] and r["name"]["confidence"] >= NAME_FLOOR)
    print("\n  Contacts")
    print(f"    emails found by the pattern   {with_email} / {len(results)}")
    print(f"    likely missed (written out)   {obfuscated}")
    print(f"    names found (confidence >= {NAME_FLOOR})  {with_name} / {len(results)}")

    fallback_found = Counter()
    for result in results.values():
        fallback_found.update(result["by_layer"].get("fallback", []))
    print(f"\n  Fallback layer contribution: {sum(fallback_found.values())} signals")
    print("    Forcing this layer is the reason one pass is viable. If it is zero,")
    print("    the forcing is wasted and you can drop the second call.")

    # ---- verdict -------------------------------------------------------
    print("\n" + "=" * 68)
    print("WHAT TO DO")
    print("=" * 68 + "\n")

    share = added_total / max(totals["both_sides"], 1)
    if share > 0.2:
        print(f"  Feed the model CUSTOMER TURNS ONLY. {share:.0%} of the signals found on the")
        print("  full transcript are absent when the agent is removed. That is too many to")
        print("  be coincidence: the agent's questions are being read as the customer's")
        print("  symptoms, and those would land in a real customer profile.\n")
    elif added_total:
        print(f"  Both sides looks safe. Only {share:.0%} of signals come from the agent's turns.")
        print("  Read the flagged files above before you commit. Keep both sides, because the")
        print("  agent's questions give meaning to a bare \"yes, exactly\".\n")
    else:
        print("  Both sides is safe. The agent's turns added no signals at all.")
        print("  Keep them, because they give meaning to a bare \"yes, exactly\".\n")

    if not args.skip_per_message:
        if sum(window_only.values()) > sum(one_pass_only.values()):
            print("  Per message still finds more than one pass. Do not drop it yet. Read the")
            print("  signals above and check whether the transcript cap is cutting them off.\n")
        else:
            print("  One pass matches or beats per message. Run detection once at session close.\n")

    print("  Nothing here is decided by the totals alone. Open two or three of the flagged")
    print("  files and read them. The numbers tell you where to look, not what is true.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
