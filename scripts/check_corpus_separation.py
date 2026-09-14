"""Check that off-brand training data is actually off-brand, before training on it.

This script exists because the first Emerson model was trained on negatives that
were not negatives, and nothing caught it. The generated "opposites" were
paraphrases: 6 of 600 identical to their source, ~60% within 0.9 cosine of it.
Training reported a healthy-looking accuracy anyway, because that number is a fit
measured on its own data — it cannot see that the two classes are the same class.

So this measures the things that number cannot:

  1. Are the classes actually apart, or do they sit on top of each other?
  2. Does a classifier trained on them generalise to examples it has not seen?
  3. Is any single negative a near-duplicate of a positive (the original bug)?

Run it before every retrain. It is cheap: on-brand vectors are reused from the
existing model artifact, so only the off-brand corpus gets embedded.

Usage:
    python scripts/check_corpus_separation.py
    python scripts/check_corpus_separation.py --off-brand path/to/other.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.tone_guard import _artifact_path, _embedding_key, _read_config  # noqa: E402

# Below this cosine, a "negative" is really just a reworded positive. 0.90 is the
# threshold that would have caught the original failure, where ~60% of generated
# opposites sat above it.
NEAR_DUPLICATE = 0.90


def _unit(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


def _load_off_brand(path: Path) -> list[str]:
    blocks = [b.strip().replace("\n", " ") for b in path.read_text(encoding="utf-8").split("\n\n")]
    return [b for b in blocks if len(b.split()) >= 5]


def _verdict(label: str, ok: bool, detail: str) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:34s} {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate off-brand training data.")
    parser.add_argument(
        "--off-brand",
        type=Path,
        default=PROJECT_ROOT / "data" / "simasia" / "emerson_off_brand_corpus.txt",
    )
    args = parser.parse_args()

    if not args.off_brand.exists():
        print(f"ERROR: no off-brand corpus at {args.off_brand}")
        print("Build one first: python scripts/build_off_brand_corpus.py")
        return 1

    config = _read_config()
    artifact = _artifact_path(config)
    if not artifact.exists():
        print(f"ERROR: no model artifact at {artifact} — needed for the on-brand vectors.")
        return 1

    key = _embedding_key()
    if not key:
        print("ERROR: no embedding key. Set EMBEDDING_KEY, or OPEN_AI_KEY in app/.env.")
        return 1

    import joblib
    from simasia import OpenAIEmbedder

    stored = joblib.load(artifact)
    on_texts: list[str] = stored["on_chunks"]
    on_vectors = _unit(np.asarray(stored["on_embeddings"], dtype=np.float64))

    off_texts = _load_off_brand(args.off_brand)
    print(f"\nOn-brand : {len(on_texts)} chunks (vectors reused from {artifact.name}, no cost)")
    print(f"Off-brand: {len(off_texts)} examples from {args.off_brand.name} — embedding now...")

    embedder = OpenAIEmbedder(model=config["embedding_model"], api_key=key)
    off_vectors = _unit(np.asarray(embedder.encode(off_texts), dtype=np.float64))

    within_on = float((on_vectors @ on_vectors.T).mean())
    within_off = float((off_vectors @ off_vectors.T).mean())
    across = float((on_vectors @ off_vectors.T).mean())
    gap = ((within_on + within_off) / 2) - across

    print("\n--- Raw similarity (context only, NOT a pass/fail signal) ---")
    print(f"  average similarity within on-brand   {within_on:+.4f}")
    print(f"  average similarity within off-brand  {within_off:+.4f}")
    print(f"  average similarity across the two    {across:+.4f}")
    print(f"  separation gap                       {gap:+.4f}")
    print(
        "  Deliberately not gated on. Measured against the old generated opposites\n"
        "  this gap read +0.000 and against known-good negatives +0.039 — a span of\n"
        "  0.04 separating coin-flip data from usable data. Averaged cosine is\n"
        "  swamped by topic variation, so it cannot see a discriminative direction\n"
        "  even when one exists. Held-out accuracy below is the metric that can."
    )

    # The original bug, stated directly: negatives that are really positives.
    worst = (on_vectors @ off_vectors.T).max(axis=0)
    duplicates = int((worst > NEAR_DUPLICATE).sum())

    # Does this generalise, or only fit? Hold out a fifth of each class, train on
    # the rest, and score only the examples the classifier never saw. This is the
    # number the training script's self-reported accuracy cannot give you.
    rng = np.random.default_rng(0)
    X = np.vstack([on_vectors, off_vectors])
    y = np.concatenate([np.ones(len(on_vectors)), np.zeros(len(off_vectors))])
    order = rng.permutation(len(y))
    X, y = X[order], y[order]
    split = len(y) // 5

    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(X[split:], y[split:])
    held_out = float(model.score(X[:split], y[:split]))

    scores = model.predict_proba(X)[:, 1]
    spread = float(scores[y == 1].mean() - scores[y == 0].mean())

    print("\n--- Does it generalise? (this is what matters) ---")
    print(f"  accuracy on unseen examples          {held_out:.3f}   (generated opposites: 0.543 — a coin flip)")
    print(f"  mean score gap (on-brand minus off)  {spread:+.3f}   (generated opposites: +0.088)")

    print("\n--- Verdict ---")
    ok = all([
        _verdict("generalises to unseen text", held_out > 0.85, f"{held_out:.3f} held-out accuracy"),
        _verdict("scores are decisive", spread > 0.30, f"{spread:+.3f} mean gap"),
        _verdict("no negative is a paraphrase", duplicates == 0, f"{duplicates} above {NEAR_DUPLICATE} cosine"),
    ])

    if ok:
        print("\nGood to train. Two-sided training makes no LLM calls — only embeddings.\n")
    else:
        print(
            "\nDo not train on this yet. A failure above means the negatives are not\n"
            "distinct enough to teach a boundary, which is exactly how the current\n"
            "model ended up unable to tell good copy from bad.\n"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
