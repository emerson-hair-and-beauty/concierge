"""Retrain the Emerson tone model that app/services/tone_guard.py scores against.

A trained model already exists at app/simasia_emerson_head.joblib (100 on-brand
chunks, 600 generated opposites, text-embedding-3-small at 1536 dimensions). You
do not need to run this to use tone ranking — it is here for refreshing the
bootstrap after the blog corpus changes, or widening it beyond 100 chunks.
Running it OVERWRITES that model.

To improve the existing model from real reviewer feedback instead, use
scripts/retrain_tone_from_feedback.py — that is the cheaper and better path.

Usage:
    python scripts/train_emerson_tone.py --dry-run          # cost preview, no API calls
    python scripts/train_emerson_tone.py --max-chunks 200   # actually retrain

The blog corpus has no off-brand counterpart, so this trains in Simasia's
**on-brand-only** mode: for every sampled chunk it generates a deliberately
off-brand opposite along each tone axis. That means chunks x dimensions
generation calls, and the full corpus is ~3,900 chunks — 23,000+ calls across all
six axes. Training therefore samples by default; --max-chunks is a cost dial, not
a quality compromise you have to accept forever.

What you get from this is a *bootstrap*: good enough to rank replies against each
other, not good enough to threshold on. It gets replaced, not merely topped up,
once real thumbs up/down accumulate — see tone_guard.train_from_feedback.

Keys: EMBEDDING_KEY, or the OPEN_AI_KEY already in app/.env. Generation reuses
the same key unless GENERATION_KEY is set.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.tone_guard import _artifact_path, _embedding_key, _read_config  # noqa: E402

# Rough public list-price anchors, used only to print an order-of-magnitude
# estimate. Wrong by a factor of two is still useful; wrong by a factor of fifty
# is what we are trying to stop someone walking into.
_USD_PER_OPPOSITE = 0.0002   # one short gpt-4o-mini completion
_USD_PER_EMBEDDING = 0.00001  # one text-embedding-3-small call


def _display(path: Path) -> str:
    """Project-relative when possible, absolute otherwise (paths may be anywhere)."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _chunks(guard, corpus_path: Path) -> list[str]:
    from simasia.sources import clean_corpus

    raw = corpus_path.read_text(encoding="utf-8")
    return guard._chunk_text(clean_corpus(raw))


def _preview(total_chunks: int, sampled: int, dimensions: list[str]) -> None:
    opposites = sampled * len(dimensions)
    embeddings = sampled + opposites
    cost = opposites * _USD_PER_OPPOSITE + embeddings * _USD_PER_EMBEDDING

    print(f"  Chunks in corpus : {total_chunks:,}")
    print(f"  Chunks sampled   : {sampled:,}")
    print(f"  Tone axes        : {len(dimensions)} ({', '.join(dimensions)})")
    print(f"  Generation calls : {opposites:,}  (one opposite per chunk per axis)")
    print(f"  Embedding calls  : {embeddings:,}")
    print(f"  Rough cost       : ~${cost:,.2f}")
    if opposites > 5000:
        print("  NOTE: this is a long run. Consider a smaller --max-chunks first.")


def main() -> int:
    config = _read_config()
    parser = argparse.ArgumentParser(description="Train the Emerson tone model.")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=PROJECT_ROOT / "data" / "simasia" / "emerson_blog_corpus.txt",
        help="On-brand text. Rebuild with scripts/build_emerson_simasia_corpus.py.",
    )
    parser.add_argument(
        "--off-brand",
        type=Path,
        default=None,
        help=(
            "Real off-brand text. Switches to two-sided training: no LLM generation "
            "at all, just embeddings. Strongly preferred — see "
            "scripts/build_off_brand_corpus.py."
        ),
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=200,
        help="Sample this many chunks (default 200). 0 uses the whole corpus.",
    )
    parser.add_argument(
        "--dimensions",
        nargs="*",
        default=None,
        help="Tone axes to flip. Default: all six.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview cost, make no API calls.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    args = parser.parse_args()

    if not args.corpus.exists():
        print(f"ERROR: corpus not found at {args.corpus}")
        print("Build it first: python scripts/build_emerson_simasia_corpus.py")
        return 1

    key = _embedding_key()
    if not key and not args.dry_run:
        print("ERROR: no embedding key. Set EMBEDDING_KEY, or OPEN_AI_KEY in app/.env.")
        return 1

    from simasia import OpenAIEmbedder, SimasiaGuard
    from simasia.guard import TONE_DIMENSIONS

    dimensions = args.dimensions if args.dimensions else list(TONE_DIMENSIONS)
    unknown = [d for d in dimensions if d not in TONE_DIMENSIONS]
    if unknown:
        print(f"ERROR: unknown tone dimension(s) {unknown}. Choose from {list(TONE_DIMENSIONS)}.")
        return 1

    artifact = _artifact_path(config)
    artifact.parent.mkdir(parents=True, exist_ok=True)

    # A stub embedder lets us chunk (and price the run) without spending anything.
    class _NullEmbedder:
        def encode(self, sentences, **_kwargs):
            import numpy as np

            return np.zeros((len(sentences), 3), dtype="float32")

    probe = SimasiaGuard(config["brand_id"], artifact_dir=str(artifact.parent), embedding_model=_NullEmbedder())
    total = len(_chunks(probe, args.corpus))
    sampled = total if args.max_chunks in (0, None) or args.max_chunks >= total else args.max_chunks

    two_sided = args.off_brand is not None
    if two_sided and not args.off_brand.exists():
        print(f"ERROR: off-brand corpus not found at {args.off_brand}")
        print("Build one first: python scripts/build_off_brand_corpus.py")
        return 1

    print(f"\nEmerson tone model  (brand_id={config['brand_id']}, embeddings={config['embedding_model']})")
    print(f"Corpus: {_display(args.corpus)}")

    if two_sided:
        # Real negatives, so nothing has to be invented: no generation calls, and
        # no risk of the paraphrase failure that produced the first model.
        off_total = len(_chunks(probe, args.off_brand))
        ratio = total / off_total if off_total else 0
        print(f"Off-brand: {_display(args.off_brand)}")
        print(f"  Mode             : two-sided (no LLM generation)")
        print(f"  On-brand chunks  : {total:,}  (whole corpus; --max-chunks does not apply)")
        print(f"  Off-brand chunks : {off_total:,}")
        print(f"  Class ratio      : {ratio:.1f} : 1  (class_weight='balanced' compensates)")
        print(f"  Embedding calls  : {total + off_total:,}")
        print(f"  Rough cost       : ~${(total + off_total) * _USD_PER_EMBEDDING:,.2f}")
        print(f"  Model size       : ~{(total + off_total) * 1536 * 4 / 1e6:.0f}MB on disk (this file goes into git)")
    else:
        print("  Mode             : on-brand only (opposites are LLM-generated)")
        _preview(total, sampled, dimensions)
        print(
            "  WARNING: this mode produced paraphrases rather than opposites last time,\n"
            "  giving a model that scored 0.543 on unseen text — a coin flip. Prefer\n"
            "  --off-brand, and run check_corpus_separation.py before trusting a result."
        )

    print(f"  Writes to        : {_display(artifact)}")

    if args.dry_run:
        print("\nDry run — nothing was called and nothing was written.\n")
        return 0

    if artifact.exists():
        print(f"\nWARNING: {artifact.name} already exists and will be overwritten.")

    if not args.yes:
        if input("\nProceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted. Nothing was spent.")
            return 1

    guard = SimasiaGuard(
        brand_id=config["brand_id"],
        artifact_dir=str(artifact.parent),
        embedding_model=OpenAIEmbedder(model=config["embedding_model"], api_key=key),
    )

    started = time.monotonic()

    def progress(done: int, total_steps: int) -> None:
        pct = 100 * done / total_steps if total_steps else 0
        print(f"\r  generating opposites: {done}/{total_steps} ({pct:.0f}%)", end="", flush=True)

    if two_sided:
        # --max-chunks is deliberately not applied here. It exists to cap how many
        # opposites get generated in on-brand-only mode, and two-sided training
        # generates nothing, so the whole corpus costs ~$0.04 and 20 seconds.
        #
        # Sampling it is also harder than it looks: chunking produces overlapping
        # two-sentence windows, so feeding back N sampled chunks re-windows into
        # roughly 2N. An earlier attempt here asked for 2,400 and trained on 4,792.
        # To train on less, trim the corpus file — that is honest about what
        # actually happens.
        accuracy = guard.train(args.corpus, off_brand=args.off_brand)
    else:
        accuracy = guard.train(
            args.corpus,
            progress=progress,
            max_chunks=None if args.max_chunks in (0, None) else args.max_chunks,
            dimensions=dimensions,
        )
    elapsed = time.monotonic() - started

    print(f"\n\nTrained in {elapsed / 60:.1f} min. Accuracy on its own training data: {accuracy:.3f}")
    print(f"Wrote {_display(artifact)}")
    print(
        "\nThat number is a fit measured on its own training data. It cannot tell you\n"
        "whether the model generalises — the previous model reported a healthy figure\n"
        "here while scoring 0.543 on unseen text. Run check_corpus_separation.py for\n"
        "the held-out number, which is the one worth believing.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
