"""Replies and expert verdicts, stored against the prompt version that produced them.

The other half of app/services/prompt_version.py. That module records what the
instructions said; this one records what came out and what a human thought of it.
Neither is much use alone: a version with no verdicts cannot be judged, and a
verdict with no version cannot be traced to the wording responsible.

What a record holds
-------------------
The reply, the customer message that prompted it, the version id, and the exact
options selected (tone, depth, structure, decision state). When the verdict comes
back it is attached to the same record.

That combination is what makes the investigation possible. If short replies keep
getting rejected, the settings are in the record. If it is one badly worded
instruction, the version resolves to its exact text. Without both, "she rejected
three of six" is an anecdote.

A note on the numbers
---------------------
`stats` reports approval rates per setting. With a handful of records these are
descriptive, not evidence: one rejection in a group of two reads as 50%. The
counts are always shown alongside so a thin group is obvious. Treat it as a
pointer to what to read, never as a finding on its own.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STORE = Path(__file__).resolve().parents[2] / "data" / "reviews"

# The dimensions a verdict can be broken down by. These are exactly the options a
# reply was generated with, so a pattern here points at a specific instruction.
DIMENSIONS = (
    "decision_state",
    "response_mode",
    "response_depth",
    "tone_profile",
    "cta_pressure",
    "product_exposure",
)


def _path(version: str) -> Path:
    return STORE / f"{version}.json"


def load(version: str) -> list[dict[str, Any]]:
    """Every recorded reply for one prompt version."""
    target = _path(version)
    if not target.exists():
        return []
    return json.loads(target.read_text(encoding="utf-8")).get("replies", [])


def load_all() -> list[dict[str, Any]]:
    """Every recorded reply across every version, newest version last."""
    if not STORE.exists():
        return []
    records: list[dict[str, Any]] = []
    for f in sorted(STORE.glob("*.json")):
        try:
            records.extend(json.loads(f.read_text(encoding="utf-8")).get("replies", []))
        except json.JSONDecodeError:
            continue
    return records


def _save(version: str, replies: list[dict[str, Any]]) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    _path(version).write_text(
        json.dumps(
            {"version": version, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "replies": replies},
            indent=1, ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def record(
    version: str,
    scenario: str,
    title: str,
    customer: str,
    reply: str,
    selected: dict[str, Any],
) -> str:
    """Save one reply. Returns its id.

    Ids read as ``ed7cedf1db2a/buildup/1``: version, scenario, and position within
    the scenario. The position matters because a pasted verdict says "Reply 2"
    with no other handle on which reply it means.
    """
    replies = load(version)
    position = sum(1 for r in replies if r["scenario"] == scenario) + 1
    entry = {
        "id": f"{version}/{scenario}/{position}",
        "version": version,
        "scenario": scenario,
        "title": title,
        "position": position,
        "customer": customer,
        "reply": reply,
        "selected": selected,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": None,
        "note": "",
    }
    replies.append(entry)
    _save(version, replies)
    return entry["id"]


def attach_verdict(version: str, title: str, position: int, verdict: str, note: str = "") -> bool:
    """Attach a human verdict to a recorded reply. Matched on title and position,
    which is all a pasted review sheet gives us."""
    replies = load(version)
    for entry in replies:
        if entry["title"] == title and entry["position"] == position:
            entry["verdict"] = verdict
            entry["note"] = note
            entry["judged_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _save(version, replies)
            return True
    return False


def stats(records: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Approval rate per setting, with counts so thin groups are visible."""
    judged = [r for r in (records if records is not None else load_all()) if r.get("verdict")]
    out: dict[str, list[dict[str, Any]]] = {}

    for dimension in DIMENSIONS:
        buckets: dict[str, list[int]] = defaultdict(list)
        for r in judged:
            value = r["selected"].get(dimension)
            if value is not None:
                buckets[value].append(1 if r["verdict"] == "yes" else 0)

        rows = [
            {
                "value": value,
                "approved": sum(votes),
                "total": len(votes),
                "rate": sum(votes) / len(votes),
            }
            for value, votes in buckets.items()
        ]
        # Worst first: what to investigate is what is failing.
        out[dimension] = sorted(rows, key=lambda r: (r["rate"], -r["total"]))

    return out


def rejected(records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every reply a human turned down. The raw material for retraining."""
    source = records if records is not None else load_all()
    return [r for r in source if r.get("verdict") == "no"]


def training_pairs(records: list[dict[str, Any]] | None = None) -> list[tuple[str, int]]:
    """Judged replies as (text, 1 for approved / 0 for rejected).

    Feeds scripts/retrain_tone_from_feedback.py. These are far better negatives
    than anything hand-written: genuinely rejected, genuinely about hair, and in
    the exact register the pipeline actually produces.
    """
    source = records if records is not None else load_all()
    return [
        (r["reply"], 1 if r["verdict"] == "yes" else 0)
        for r in source
        if r.get("verdict") in ("yes", "no")
    ]
