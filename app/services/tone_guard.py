"""
Emerson tone guardrail — the app-side wrapper around Simasia.

Simasia answers one question: "does this text sound like Emerson?", as a score in
[0, 1]. It never calls our LLM; we generate candidate replies, it ranks them.

Three things this module owns that Simasia deliberately does not:

1. **Config**, read once from ``simasia.toml`` so the brand id, artifact dir, and
   embedding model cannot drift between training and scoring. A vector from one
   embedding model is meaningless against another — a mismatch does not raise, it
   silently returns garbage scores, so the same file feeds both paths.
2. **The key name.** Simasia reads ``EMBEDDING_KEY``; this codebase has always
   stored the OpenAI key as ``OPEN_AI_KEY``/``OPENAI_API_KEY`` (see app/config.py).
   We bridge the two rather than asking anyone to set the same secret twice.
3. **Degradation.** Tone ranking is a quality improvement, not a correctness
   requirement. An untrained model, a missing key, or an embedding outage must
   cost us the ranking, never the reply. Every failure path here returns "no
   opinion" and is logged loudly, following app/services/resilience.py.

The trained artifact is a file (.simasia/, gitignored). It is loaded once per
process and cached, so scoring does not touch storage on every call. If this ever
runs across several containers, swap FileArtifactStore for a shared ArtifactStore
implementation — nothing else in this module changes.
"""
from __future__ import annotations

import os
import threading
import tomllib
from pathlib import Path
from typing import Any

from app.services.resilience import record_degraded_call as _record_degraded_call

_CONSEQUENCE = (
    "Tone ranking is a quality layer, not a correctness one — replies still\n"
    "  ship, unranked, and may drift off Emerson's voice until this recovers."
)


def _record(source: str, detail: str, error: Exception) -> None:
    _record_degraded_call(source, detail, error, subsystem="Tone model", consequence=_CONSEQUENCE)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _PROJECT_ROOT / "simasia.toml"

# Fallbacks only matter if simasia.toml is missing entirely; they mirror the
# values committed in that file so behaviour stays identical either way.
_DEFAULTS = {
    "brand_id": "emerson",
    "artifact_dir": "app",
    "embedding_model": "text-embedding-3-small",
}

_guard: Any | None = None
_load_attempted = False
_lock = threading.Lock()


def _read_config() -> dict[str, str]:
    try:
        with _CONFIG_PATH.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        return dict(_DEFAULTS)

    return {
        "brand_id": raw.get("brand", {}).get("id", _DEFAULTS["brand_id"]),
        "artifact_dir": raw.get("storage", {}).get("dir", _DEFAULTS["artifact_dir"]),
        "embedding_model": raw.get("embedding", {}).get("model", _DEFAULTS["embedding_model"]),
    }


def _embedding_key() -> str:
    """Resolve the embedding key, loading app/.env the way app/config.py does.

    Not imported from app.config on purpose: that module raises at import time
    when the active LLM provider's key is missing. Tone ranking must degrade
    quietly rather than take the process down over a key it does not even use, so
    it repeats the small amount of dotenv work instead of inheriting that.
    """
    if not os.getenv("EMBEDDING_KEY") and not os.getenv("OPENAI_API_KEY") and not os.getenv("OPEN_AI_KEY"):
        try:
            from dotenv import load_dotenv

            load_dotenv(_PROJECT_ROOT / "app" / ".env")
        except ImportError:
            pass

    return (
        os.getenv("EMBEDDING_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("OPEN_AI_KEY", "")
    )


def _artifact_path(config: dict[str, str]) -> Path:
    directory = Path(config["artifact_dir"])
    if not directory.is_absolute():
        directory = _PROJECT_ROOT / directory
    return directory / f"simasia_{config['brand_id']}_head.joblib"


def _load_guard() -> Any | None:
    """Build the guard once. Returns None if tone ranking is unavailable.

    Unavailable is a normal, expected state — nobody has trained the model yet, or
    this deployment has no embedding key. It is reported once, not per reply.
    """
    global _guard, _load_attempted

    if _load_attempted:
        return _guard

    with _lock:
        if _load_attempted:
            return _guard
        _load_attempted = True

        config = _read_config()
        artifact = _artifact_path(config)

        if not artifact.exists():
            print(
                f"[TONE GUARD] No trained model at {artifact} — tone ranking is off. "
                f"Replies are unaffected. Train with: python scripts/train_emerson_tone.py"
            )
            return None

        key = _embedding_key()
        if not key:
            print(
                "[TONE GUARD] No embedding key (EMBEDDING_KEY / OPENAI_API_KEY / "
                "OPEN_AI_KEY) — tone ranking is off. Replies are unaffected."
            )
            return None

        try:
            from simasia import OpenAIEmbedder, SimasiaGuard

            _guard = SimasiaGuard(
                brand_id=config["brand_id"],
                artifact_dir=str(artifact.parent),
                embedding_model=OpenAIEmbedder(model=config["embedding_model"], api_key=key),
            )
        except Exception as e:
            _record(
                "tone_guard._load_guard",
                "Simasia failed to load; replies ship unranked for the life of this process",
                e,
            )
            _guard = None

        return _guard


def is_available() -> bool:
    """True if a trained model is loaded and scoring can happen."""
    return _load_guard() is not None


def reset_cache() -> None:
    """Drop the cached guard so the next call reloads it.

    For tests, and for picking up a freshly trained model without a restart.
    """
    global _guard, _load_attempted
    with _lock:
        _guard = None
        _load_attempted = False


def score(text: str) -> float | None:
    """How on-brand `text` is, in [0, 1]. None when tone ranking is unavailable.

    Costs one embedding call. Callers must treat None as "no opinion" rather than
    as a low score — an outage is not evidence that a reply is off-brand.
    """
    guard = _load_guard()
    if guard is None or not text.strip():
        return None
    try:
        return float(guard.evaluate_response(text))
    except Exception as e:
        _record("tone_guard.score", "reply shipped without a tone score", e)
        return None


def explain(text: str) -> dict | None:
    """Score plus the nearest on-brand and off-brand training examples.

    For humans reading the dashboard — the comparison itself happens between
    vectors, not the returned text. No LLM call.
    """
    guard = _load_guard()
    if guard is None or not text.strip():
        return None
    try:
        return guard.explain(text)
    except Exception as e:
        _record("tone_guard.explain", "no tone explanation available", e)
        return None


def diagnose(text: str) -> dict | None:
    """Score `text` and name *how* it went off-brand, ready to feed into a retry.

    Returns ``{"score", "register", "guidance", "example"}``, or None when tone
    ranking is unavailable.

    Built from the nearest **off-brand** neighbour, deliberately not the nearest
    on-brand one. The on-brand neighbour is a chunk of blog prose; handing that
    back as a "write like this" target would pull replies toward editorial
    register, which is already this model's weakest spot — it was trained on
    long-form articles and scores terse, direct replies lower than they deserve.
    The off-brand neighbour is the useful half: it says which way the reply
    drifted, and because the corpus is written in labelled registers we can turn
    that into a specific instruction instead of "be more on-brand".

    `example` is returned for logging and dashboards. Do not paste it into a
    prompt — showing a model off-brand text tends to echo it back.
    """
    guard = _load_guard()
    if guard is None or not text.strip():
        return None

    try:
        explanation = guard.explain(text)
    except Exception as e:
        _record("tone_guard.diagnose", "no tone diagnosis available", e)
        return None

    from app.services.tone_registers import classify, guidance_for

    neighbour = (explanation.get("closest_off_brand") or {}).get("text", "")
    register = classify(neighbour) if neighbour else None

    return {
        "score": float(explanation["score"]),
        "register": register,
        "guidance": guidance_for(register),
        "example": neighbour,
    }


def pick_best(candidates: list[str]) -> dict:
    """Rank `candidates` and return the most on-brand one.

    Returns ``{"text", "score", "ranked", "guarded"}``. ``guarded`` is False when
    ranking could not run, in which case ``text`` is the first candidate — the
    same reply the caller would have shipped without this module — and ``score``
    is None.

    Ranking is the reliable way to use Simasia: it only orders candidates against
    each other, so it works even while absolute scores are poorly calibrated (as
    they are for a bootstrap model trained on generated opposites). Do not build a
    pass/fail threshold on ``score`` until the model has been retrained on real
    thumbs up/down.
    """
    usable = [c for c in candidates if c and c.strip()]
    if not usable:
        return {"text": "", "score": None, "ranked": [], "guarded": False}

    fallback = {"text": usable[0], "score": None, "ranked": [], "guarded": False}

    guard = _load_guard()
    if guard is None or len(usable) == 1:
        return fallback

    try:
        result = guard.pick_best(usable)
    except Exception as e:
        _record(
            "tone_guard.pick_best",
            f"shipped the first of {len(usable)} candidates unranked",
            e,
        )
        return fallback

    return {
        "text": result["text"],
        "score": result.get("score"),
        "ranked": result.get("ranked", []),
        "guarded": True,
    }


def train_from_feedback(examples: list[tuple[str, int]], include_existing: bool = False) -> float | None:
    """Fold thumbs up (1) / thumbs down (0) on tone into the model.

    Each reply is one example, embedded as-is. Pass ``include_existing=True`` to
    add a batch on top of what the model already knows.

    Once enough real feedback has accumulated, retrain with
    ``include_existing=False`` on the pure feedback set. That drops the synthetic
    bootstrap entirely and is the point at which the model stops guessing the
    voice and starts reflecting what users actually approve — and the point at
    which absolute scores become trustworthy enough to threshold on.

    Unlike the read paths above this raises on failure: a training run that
    silently did nothing is worse than one that stops and says so.
    """
    if not examples:
        return None
    guard = _load_guard()
    if guard is None:
        raise RuntimeError(
            "Cannot train from feedback: no trained model loaded. Run "
            "python scripts/train_emerson_tone.py first."
        )
    accuracy = float(guard.train_from_labeled(examples, include_existing=include_existing))
    reset_cache()  # the artifact on disk changed; reload it on next use
    return accuracy
