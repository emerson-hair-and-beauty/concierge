"""Save, list and diff versions of the composer's instructions.

Run this before generating replies for review. Every reply then carries an id
that resolves to the exact wording that produced it, so a verdict weeks later can
be traced to the sentence responsible.

Versions are content-derived. Saving twice without editing anything is a no-op,
and any wording change makes a new one, so there is nothing to remember to bump.

Usage:
    python scripts/prompt_versions.py                     save the current wording
    python scripts/prompt_versions.py -m "split tone/voice"
    python scripts/prompt_versions.py --list
    python scripts/prompt_versions.py --show a3f91c2b8d04
    python scripts/prompt_versions.py --diff a3f91c2b8d04 b7c25e9f1a36
    python scripts/prompt_versions.py --diff-last        current vs last saved
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services import prompt_version as pv  # noqa: E402

STORE = PROJECT_ROOT / "data" / "prompt_versions"


def _path(version_id: str) -> Path:
    return STORE / f"{version_id}.json"


def _saved() -> list[dict]:
    if not STORE.exists():
        return []
    records = []
    for f in STORE.glob("*.json"):
        try:
            records.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print(f"  (skipping unreadable {f.name})")
    return sorted(records, key=lambda r: r.get("captured_at", ""))


def save(note: str) -> int:
    snap = pv.snapshot(note)
    STORE.mkdir(parents=True, exist_ok=True)
    target = _path(snap["id"])

    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        print(f"\nAlready saved as {snap['id']} on {existing['captured_at']}.")
        print("Nothing has changed since, so there is nothing to record.\n")
        return 0

    previous = _saved()
    target.write_text(json.dumps(snap, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\nSaved version {snap['id']}")
    print(f"  {snap['counts']['blocks']} blocks, {snap['counts']['options']} options "
          f"across {snap['counts']['tables']} tables")
    if note:
        print(f"  note: {note}")

    if previous:
        changes = pv.diff(previous[-1], snap)
        print(f"\nChanged since {previous[-1]['id']}:")
        for kind in ("changed", "added", "removed"):
            for name in changes[kind]:
                print(f"  {kind:8s} {name}")
    print()
    return 0


def show(version_id: str) -> int:
    target = _path(version_id)
    if not target.exists():
        print(f"No saved version {version_id}. Try --list.")
        return 1
    snap = json.loads(target.read_text(encoding="utf-8"))
    print(f"\n{snap['id']}  captured {snap['captured_at']}")
    if snap.get("note"):
        print(f"note: {snap['note']}")
    for name, text in sorted(pv.flatten(snap).items()):
        print(f"\n--- {name} ---")
        print(text)
    print()
    return 0


def listing() -> int:
    records = _saved()
    if not records:
        print("\nNothing saved yet. Run without arguments to save the current wording.\n")
        return 0
    current = pv.version_id()
    print(f"\n{len(records)} saved version(s):\n")
    for r in records:
        here = "  <- current wording" if r["id"] == current else ""
        print(f"  {r['id']}  {r['captured_at'][:16].replace('T', ' ')}  "
              f"{r['counts']['options']:3d} options{here}")
        if r.get("note"):
            print(f"                 {r['note']}")
    if current not in {r["id"] for r in records}:
        print(f"\n  The current wording ({current}) is NOT saved. Run without arguments.")
    print()
    return 0


def _load(version_id: str) -> dict | None:
    target = _path(version_id)
    if not target.exists():
        print(f"No saved version {version_id}. Try --list.")
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def show_diff(older: dict, newer: dict, a_label: str, b_label: str) -> int:
    changes = pv.diff(older, newer)
    total = sum(len(v) for v in changes.values())
    print(f"\n{a_label} -> {b_label}: {total} instruction(s) differ\n")
    if not total:
        print("  Identical wording.\n")
        return 0

    flat_a, flat_b = pv.flatten(older), pv.flatten(newer)
    for name in changes["changed"]:
        print(f"--- {name} ---")
        for line in difflib.unified_diff(
            flat_a[name].splitlines(), flat_b[name].splitlines(),
            lineterm="", n=1, fromfile=a_label, tofile=b_label,
        ):
            print(f"  {line}")
        print()
    for name in changes["added"]:
        print(f"+++ added   {name}\n  {flat_b[name][:200]}\n")
    for name in changes["removed"]:
        print(f"--- removed {name}\n  {flat_a[name][:200]}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Version the composer's instructions.")
    parser.add_argument("-m", "--note", default="", help="Why this version exists.")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--show", metavar="ID")
    parser.add_argument("--diff", nargs=2, metavar=("OLD", "NEW"))
    parser.add_argument("--diff-last", action="store_true",
                        help="Compare the current wording against the last saved version.")
    args = parser.parse_args()

    if args.list:
        return listing()
    if args.show:
        return show(args.show)
    if args.diff:
        older, newer = _load(args.diff[0]), _load(args.diff[1])
        return 1 if older is None or newer is None else show_diff(older, newer, args.diff[0], args.diff[1])
    if args.diff_last:
        records = _saved()
        if not records:
            print("\nNothing saved to compare against.\n")
            return 1
        current = pv.snapshot()
        return show_diff(records[-1], current, records[-1]["id"], f"{current['id']} (unsaved)")

    return save(args.note)


if __name__ == "__main__":
    raise SystemExit(main())
