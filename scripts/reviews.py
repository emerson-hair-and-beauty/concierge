"""Record replies, import expert verdicts, and look for patterns in what failed.

The investigative loop:

    python scripts/reviews.py record              generate replies, save against
                                                  the current prompt version
    python scripts/reviews.py import verdicts.txt paste back what the expert sent
    python scripts/reviews.py stats               which settings get rejected
    python scripts/reviews.py rejected            read every reply she turned down

`import` reads the exact text the review page produces, so the expert's workflow
is: click through, press "Copy my answers", paste into a file, send it. No form to
fill in, no format to learn.

Everything is keyed to a prompt version, so a verdict can always be traced back to
the wording that caused it. Change an instruction, record a new batch, and the two
sets are comparable.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.services import prompt_version, review_store, tone_rules  # noqa: E402


async def _clean_reply(rc, prompt: str, temperature: float, attempts: int) -> tuple[str, list[dict]]:
    """Generate until `tone_rules.check()` is clean, or return the last try with its faults.

    Lexical rules only, deliberately. Banned words, hedges and dashes are exact,
    free, and Emerson's own stated rules, so there is no reason to spend the
    expert's attention on a reply that breaks one.

    `tone_guard` and `tone_judge` are kept out on purpose. tone_guard scores
    generic hair copy 0.949 and a good short reply 0.588, so filtering by it
    would hand her the longest reply every time and quietly settle the open
    "short versus educational" question on its own. tone_judge is the thing being
    validated against her verdicts, so using it to choose what she sees would
    make that validation circular.

    A repeat offence escalates. `_retry_prompt` rebuilds from the base prompt
    every time, so re-sending the same guidance for the same fault is literally
    the same request again: one em dash survived six attempts that way. From the
    second failure on, the note names the exact characters and says the previous
    draft already lost them.
    """
    current = prompt
    text, violations = "", []
    seen: set[str] = set()

    for _ in range(max(1, attempts)):
        text, _usage = await rc._collect(current, temperature)
        if not text.strip():
            continue
        violations = tone_rules.check(text)
        if not violations:
            return text, []

        guidance = tone_rules.guidance(violations)
        repeats = sorted({f for v in violations for f in v["found"]} & seen)
        if repeats:
            quoted = ", ".join(f'"{f}"' for f in repeats)
            guidance += (
                f"\nA previous draft was already rejected for {quoted} and the rewrite kept "
                f"it. Do not write {quoted} anywhere in the reply, in any position, including "
                "inside brackets or as an aside. Where you would reach for it, use a full stop "
                "and start a new sentence."
            )
        seen.update(f for v in violations for f in v["found"])
        current = rc._retry_prompt(prompt, guidance)

    return text, violations

# Human-readable titles, shared with the review page so a pasted sheet matches.
# Titles MUST be unique across scenarios. `attach_verdict` matches a pasted
# verdict on title plus position, because that is all a named review sheet gives
# it. Two scenarios once shared "Hair snapping when detangling", and two verdicts
# meant for `repair_breakage` were written onto `breakage` instead. Nothing
# failed; the data was simply wrong.
TITLES = {
    # Superseded by the `repair_breakage` routing case, which drives the same
    # question through the real pipeline instead of a hand-written state.
    "breakage": "Hair snapping when detangling (hand-built scenario)",
    "buildup": "Products stopped absorbing",
    "coated": "Hair feels heavy and dull",
    "climate": "Definition gone by lunchtime",
    "frustrated": "Ready to give up",
}

_duplicates = {t for t in TITLES.values() if list(TITLES.values()).count(t) > 1}
if _duplicates:
    raise RuntimeError(
        f"Two scenarios share a title: {sorted(_duplicates)}. Verdicts are matched on "
        "title and position, so a shared title silently attaches a verdict to the wrong reply."
    )


def cmd_record(args) -> int:
    from evaluate_tone_ranking import SCENARIOS

    from app.services.decision_state import response_composer as rc

    chosen = dict(SCENARIOS)
    if args.scenario:
        unknown = set(args.scenario) - set(SCENARIOS)
        if unknown:
            print(f"\nNo such scenario: {', '.join(sorted(unknown))}")
            print(f"Known: {', '.join(sorted(SCENARIOS))}\n")
            return 1
        chosen = {k: SCENARIOS[k] for k in SCENARIOS if k in set(args.scenario)}

    version = prompt_version.version_id()
    print(f"\nRecording against prompt version {version}")
    print(f"  {len(chosen)} scenario(s) x {args.runs} run(s): {', '.join(chosen)}")
    if not (PROJECT_ROOT / "data" / "prompt_versions" / f"{version}.json").exists():
        print("  WARNING: this version is not saved. Run scripts/prompt_versions.py first,")
        print("  or the wording behind these replies cannot be read back later.\n")

    async def go() -> None:
        for key, ci in chosen.items():
            prompt = rc.render_response_prompt(ci)
            results = await asyncio.gather(
                *(_clean_reply(rc, prompt, args.temperature, args.attempts) for _ in range(args.runs))
            )
            for text, violations in results:
                if not text.strip():
                    continue
                rid = review_store.record(
                    version=version,
                    scenario=key,
                    title=TITLES.get(key, key),
                    customer=ci.recent_messages[-1]["content"],
                    reply=text.strip(),
                    selected=prompt_version.stamp(ci)["selected"],
                )
                if violations:
                    faults = "; ".join(f"{v['category']}: {', '.join(v['found'])}" for v in violations)
                    print(f"  {rid}   STILL BREAKS A RULE after {args.attempts} tries -> {faults}")
                else:
                    print(f"  {rid}")
            await asyncio.sleep(args.pause)

    asyncio.run(go())
    print(f"\nSaved to data/reviews/{version}.json\n")
    return 0


_VERSION_LINE = re.compile(r"instruction set:\s*([0-9a-f]{6,})", re.I)
_REPLY_LINE = re.compile(r"^\s*Reply\s+(\d+):\s*(.+?)\s*$", re.I)
_NOTE_LINE = re.compile(r"^\s*note:\s*(.*)$", re.I)

_VERDICTS = {
    "sounds like us": "yes",
    "does not sound like us": "no",
    "doesn't sound like us": "no",
    "not rated": None,
}


_TICKET_LINE = re.compile(r"^\s*(r\d+):\s*(.+?)\s*$", re.I)


def cmd_import(args) -> int:
    """Parse the text a review page produces and attach the verdicts.

    Two formats, because there are two pages. The named page groups replies under
    a question heading and numbers them ("Reply 2: ..."). The blind page hides the
    question grouping and uses opaque tickets ("r7: ..."), which are resolved via
    data/reviews/_tickets.json. Ticket format is tried first: it is unambiguous,
    and it is the one that carries a blind comparison.
    """
    text = Path(args.file).read_text(encoding="utf-8")
    lines = text.splitlines()

    # Checked per line: _TICKET_LINE is anchored, so searching the whole blob
    # only ever tests the first line.
    if any(_TICKET_LINE.match(line) for line in lines):
        return _import_tickets(lines)

    found = _VERSION_LINE.search(text)
    version = args.version or (found.group(1) if found else None)
    if not version:
        print("\nNo version in the file and none given. Pass --version.")
        print("Without it, these verdicts cannot be tied to any wording.\n")
        return 1

    known = {r["title"] for r in review_store.load(version)}
    if not known:
        print(f"\nNo recorded replies for version {version}. Run `record` first.\n")
        return 1

    title = None
    pending: tuple[int, str] | None = None
    attached = missed = skipped = 0

    def flush(note: str = "") -> None:
        nonlocal attached, missed, pending
        if pending is None:
            return
        position, verdict = pending
        pending = None
        if review_store.attach_verdict(version, title, position, verdict, note):
            attached += 1
            print(f"  {verdict:3s}  {title} / reply {position}" + (f"  ({note[:60]})" if note else ""))
        else:
            missed += 1
            print(f"  ??   no recorded reply for {title!r} / reply {position}")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        note_match = _NOTE_LINE.match(line)
        if note_match and pending is not None:
            flush(note_match.group(1).strip())
            continue

        reply_match = _REPLY_LINE.match(line)
        if reply_match and title:
            flush()
            verdict = _VERDICTS.get(reply_match.group(2).strip().lower())
            if verdict is None:
                skipped += 1
                continue
            pending = (int(reply_match.group(1)), verdict)
            continue

        if stripped in known:
            flush()
            title = stripped

    flush()

    print(f"\n{attached} verdict(s) attached to version {version}")
    if skipped:
        print(f"{skipped} left unrated")
    if missed:
        print(f"{missed} could not be matched. Check the titles line up with what was recorded.")
    print()
    return 0 if attached else 1


def _import_tickets(lines: list[str]) -> int:
    """Attach verdicts keyed by the blind page's opaque tickets."""
    import json

    key_path = PROJECT_ROOT / "data" / "reviews" / "_tickets.json"
    if not key_path.exists():
        print("\nNo ticket map at data/reviews/_tickets.json.")
        print("It is written by build_blind_review.py and is the only way back from r7 to a reply.\n")
        return 1
    tickets = json.loads(key_path.read_text(encoding="utf-8"))

    by_id = {r["id"]: r for r in review_store.load_all()}
    attached = missed = skipped = 0
    pending: tuple[str, str] | None = None

    def flush(note: str = "") -> None:
        nonlocal attached, missed, pending
        if pending is None:
            return
        ticket, verdict = pending
        pending = None
        record = by_id.get(tickets.get(ticket, ""))
        if record is None:
            missed += 1
            print(f"  ??   {ticket} is not in the ticket map")
            return
        if review_store.attach_verdict(record["version"], record["title"], record["position"], verdict, note):
            attached += 1
            print(f"  {verdict:3s}  {ticket} -> {record['version'][:6]} / {record['scenario']}"
                  + (f"  ({note[:50]})" if note else ""))
        else:
            missed += 1
            print(f"  ??   could not attach {ticket}")

    for line in lines:
        note_match = _NOTE_LINE.match(line)
        if note_match and pending is not None:
            flush(note_match.group(1).strip())
            continue

        ticket_match = _TICKET_LINE.match(line)
        if ticket_match:
            flush()
            verdict = _VERDICTS.get(ticket_match.group(2).strip().lower())
            if verdict is None:
                skipped += 1
                continue
            pending = (ticket_match.group(1).lower(), verdict)

    flush()

    print(f"\n{attached} verdict(s) attached")
    if skipped:
        print(f"{skipped} left unrated")
    if missed:
        print(f"{missed} could not be matched")
    print()
    return 0 if attached else 1


def cmd_stats(args) -> int:
    records = review_store.load(args.version) if args.version else review_store.load_all()
    judged = [r for r in records if r.get("verdict")]
    if not judged:
        print("\nNo verdicts yet. Import some first.\n")
        return 1

    approved = sum(1 for r in judged if r["verdict"] == "yes")
    print(f"\n{approved} of {len(judged)} replies approved "
          f"({100 * approved / len(judged):.0f}%)\n")

    for dimension, rows in review_store.stats(judged).items():
        if len(rows) < 1:
            continue
        print(f"{dimension}")
        for row in rows:
            bar = "#" * round(row["rate"] * 10)
            thin = "   (only 1 reply)" if row["total"] == 1 else ""
            print(f"  {row['value']:32s} {row['approved']}/{row['total']}  "
                  f"{bar:<10s} {100 * row['rate']:3.0f}%{thin}")
        print()

    print("Small numbers. Read these as a pointer to what to look at, not as a finding.\n")
    return 0


def cmd_rejected(args) -> int:
    records = review_store.load(args.version) if args.version else review_store.load_all()
    turned_down = review_store.rejected(records)
    if not turned_down:
        print("\nNothing rejected yet.\n")
        return 0

    print(f"\n{len(turned_down)} rejected reply(s):\n")
    for r in turned_down:
        picks = r["selected"]
        print(f"--- {r['id']}")
        print(f"    settings : {picks.get('tone_profile')} / {picks.get('response_depth')} / "
              f"{picks.get('response_mode')} / {picks.get('decision_state')}")
        print(f"    customer : {r['customer']}")
        print(f"    reply    : {r['reply'][:200]}")
        if r.get("note"):
            print(f"    why      : {r['note']}")
        print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Record replies and expert verdicts.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("record", help="Generate replies and save them against the current version.")
    p.add_argument(
        "--scenario", action="append",
        help="Record only this scenario. Repeatable. Default: all. Rounds are three "
             "scenarios x two runs, which is six cards and about 15 minutes of her time.",
    )
    p.add_argument("--runs", type=int, default=2, help="Replies per scenario.")
    p.add_argument(
        "--attempts", type=int, default=3,
        help="Regenerations allowed per reply while it still breaks a lexical rule.",
    )
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--pause", type=float, default=12)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("import", help="Attach verdicts from a pasted review sheet.")
    p.add_argument("file")
    p.add_argument("--version", help="Override the version in the file.")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("stats", help="Approval rate broken down by setting.")
    p.add_argument("--version")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("rejected", help="Read every reply that was turned down.")
    p.add_argument("--version")
    p.set_defaults(func=cmd_rejected)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
