"""Fold dashboard thumbs up/down into the Emerson tone model.

Usage:
    python scripts/retrain_tone_from_feedback.py --dry-run   # show what would be used
    python scripts/retrain_tone_from_feedback.py             # add feedback to the model
    python scripts/retrain_tone_from_feedback.py --replace   # drop the bootstrap entirely

This closes the loop the bootstrap only approximates. Training on generated
opposites teaches the model what Emerson's voice is *not*, by construction; real
feedback teaches it what reviewers actually approve. Once enough has accumulated,
--replace retrains on the pure feedback set and discards the synthetic examples —
that is the point at which absolute scores become worth thresholding on, rather
than only ranking with.

READ THIS BEFORE TRUSTING THE OUTPUT
------------------------------------
The dashboard asks "Was this response good?" — one thumb covering accuracy,
usefulness, and tone together. Simasia only models tone. A reply thumbed down for
recommending the wrong product therefore enters the model as "off-brand voice",
which it may not be.

That mismatch is tolerable for a handful of examples and corrosive at scale. If
tone ranking becomes load-bearing, split the dashboard control into a separate
tone judgement and feed only that here. Until then, keep --replace for when the
tone-specific signal is genuinely large; prefer the default additive mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services import tone_guard  # noqa: E402

_RATING_LABELS = {"positive": 1, "negative": 0}


def _display(path: Path) -> str:
    """Project-relative when possible, absolute otherwise (paths may be anywhere)."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_examples(path: Path, min_words: int) -> tuple[list[tuple[str, int]], Counter]:
    """Read the feedback log into (text, label) pairs, newest wins per response.

    The log is append-only, so the same response can appear more than once if a
    reviewer changed their mind. Later entries overwrite earlier ones rather than
    training the model on both sides of the same example.
    """
    skipped: Counter = Counter()
    latest: dict[str, int] = {}

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            skipped["malformed json"] += 1
            continue

        text = (entry.get("response") or "").strip()
        label = _RATING_LABELS.get(entry.get("rating"))

        if label is None:
            skipped["no usable rating"] += 1
        elif not text:
            skipped["empty response"] += 1
        elif len(text.split()) < min_words:
            skipped[f"under {min_words} words"] += 1
        else:
            latest[text] = label

    return list(latest.items()), skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrain the tone model from dashboard feedback.")
    parser.add_argument(
        "--feedback",
        type=Path,
        default=PROJECT_ROOT / "feedback_log.jsonl",
        help="Feedback log written by the dashboard.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Train on feedback alone, discarding the synthetic bootstrap.",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=15,
        help="Ignore very short replies (default 15 words) — too little signal to embed.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would be used, train nothing.")
    args = parser.parse_args()

    if not args.feedback.exists():
        print(f"No feedback log at {args.feedback} — nothing to learn from yet.")
        return 1

    examples, skipped = load_examples(args.feedback, args.min_words)
    thumbs_up = sum(label for _, label in examples)
    thumbs_down = len(examples) - thumbs_up

    print(f"\nFeedback: {_display(args.feedback)}")
    print(f"  Usable examples : {len(examples)}  ({thumbs_up} up / {thumbs_down} down)")
    for reason, count in skipped.most_common():
        print(f"  Skipped         : {count} ({reason})")

    if not examples:
        print("\nNothing usable in the log yet.\n")
        return 1

    # A logistic head needs both classes; one-sided feedback cannot define a
    # boundary, and --replace on one-sided data would destroy a working model.
    if thumbs_up == 0 or thumbs_down == 0:
        print(
            "\nERROR: feedback is entirely one-sided. The model needs examples of both\n"
            "on-brand and off-brand voice to learn a boundary. Collect the other side first.\n"
        )
        return 1

    mode = "REPLACE the current model" if args.replace else "ADD to the current model"
    print(f"  Mode            : {mode}")

    if args.replace and len(examples) < 40:
        print(
            f"\nWARNING: --replace with only {len(examples)} examples discards the bootstrap\n"
            f"in favour of a very small training set. Additive mode is usually better here."
        )

    if args.dry_run:
        print("\nDry run — the model was not touched.\n")
        return 0

    if not tone_guard.is_available():
        print(
            "\nERROR: no trained model to update. Run scripts/train_emerson_tone.py first —\n"
            "feedback refines the bootstrap, it does not replace the initial training.\n"
        )
        return 1

    accuracy = tone_guard.train_from_feedback(examples, include_existing=not args.replace)
    print(f"\nRetrained. Accuracy on the training set: {accuracy:.3f}")
    print(
        "Measured on the data it just fit, so it says the classes are separable —\n"
        "not that the model generalises. Judge it by whether the replies it ranks\n"
        "first actually read better.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
