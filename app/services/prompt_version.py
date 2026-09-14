"""A content-derived version for the composer's instructions.

Why
---
Replies are judged days after they are written, and the prompt keeps changing in
between. Without a version stamped on each reply, "the expert rejected this one"
cannot be traced back to the wording that caused it, and the whole review
exercise turns into anecdote.

So every instruction that shapes a reply is collected, hashed, and saved. A reply
records the id; the id resolves to the exact text of every instruction at that
moment; two ids can be diffed to show precisely which wording changed.

What counts as the version
--------------------------
Everything in response_composer that feeds the prompt: the always-on blocks
(voice, philosophy, footer) and every option in every table (each tone, each
depth, each structure, each decision-state note). Change one word in one option
and the id changes, because that word can change a reply.

Discovered by inspection rather than by a hardcoded list. A version that silently
omits a newly added block would be worse than no version at all, since it would
report "nothing changed" when something had.

Deliberately excluded: the assembled templates. They are the frame the
instructions are poured into, and they carry {placeholders} rather than
instruction text. They are still tracked, but as their own field, so a template
edit is visible without drowning the diff in scaffolding.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

# Blocks shorter than this are labels or separators, not instructions.
_MIN_BLOCK = 40
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def collect() -> dict[str, Any]:
    """Gather every instruction that shapes a reply, grouped by kind.

    Returns ``{"blocks": {...}, "tables": {name: {option: text}}, "templates": {...}}``.
    """
    from app.services.decision_state import response_composer as rc

    blocks: dict[str, str] = {}
    tables: dict[str, dict[str, str]] = {}
    templates: dict[str, str] = {}

    for name in dir(rc):
        if not name.startswith("_") or name.startswith("__"):
            continue
        value = getattr(rc, name)
        key = name.strip("_").lower()

        if isinstance(value, str) and len(value) >= _MIN_BLOCK:
            (templates if _PLACEHOLDER.search(value) else blocks)[key] = value
        elif isinstance(value, dict) and value and all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            tables[key] = dict(value)

    return {"blocks": blocks, "tables": tables, "templates": templates}


def _canonical(parts: dict[str, Any]) -> str:
    """Stable text form. Sorted keys so dict ordering never shifts the id."""
    return json.dumps(parts, sort_keys=True, ensure_ascii=False)


def version_id(parts: dict[str, Any] | None = None) -> str:
    """Short content hash of the instructions. Same wording, same id, always."""
    return hashlib.sha256(_canonical(parts or collect()).encode("utf-8")).hexdigest()[:12]


def snapshot(note: str = "") -> dict[str, Any]:
    """A full, self-contained record of the instructions as they are right now."""
    parts = collect()
    return {
        "id": version_id(parts),
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": note,
        "counts": {
            "blocks": len(parts["blocks"]),
            "tables": len(parts["tables"]),
            "options": sum(len(t) for t in parts["tables"].values()),
        },
        **parts,
    }


def flatten(parts: dict[str, Any]) -> dict[str, str]:
    """One flat name -> text map, for diffing.

    Names read as ``tone_instructions:warm_reassuring`` so a diff points at the
    exact option that changed rather than at a whole table.
    """
    flat = {f"block:{k}": v for k, v in parts.get("blocks", {}).items()}
    flat.update({f"template:{k}": v for k, v in parts.get("templates", {}).items()})
    for table, options in parts.get("tables", {}).items():
        for option, text in options.items():
            flat[f"{table}:{option}"] = text
    return flat


def diff(older: dict[str, Any], newer: dict[str, Any]) -> dict[str, list]:
    """What wording changed between two snapshots."""
    a, b = flatten(older), flatten(newer)
    return {
        "added": sorted(set(b) - set(a)),
        "removed": sorted(set(a) - set(b)),
        "changed": sorted(k for k in set(a) & set(b) if a[k] != b[k]),
    }


def stamp(composer_input=None) -> dict[str, Any]:
    """The provenance to record alongside a generated reply.

    Carries the version id plus the options actually selected for this reply, so
    a rejected reply can be traced to both the wording in force and the settings
    that chose it. Both matter: an instruction can be badly written, or correctly
    written and wrongly selected.
    """
    record: dict[str, Any] = {"prompt_version": version_id()}
    if composer_input is None:
        return record

    plan = composer_input.jte_delivery_plan
    record["selected"] = {
        "decision_state": composer_input.strategy_payload.decision_state,
        "response_mode": plan.response_mode,
        "response_depth": plan.response_depth,
        "tone_profile": plan.tone_profile,
        "cta_pressure": plan.cta_pressure,
        "product_exposure": plan.product_exposure,
    }
    return record
