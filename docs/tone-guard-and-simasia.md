# Tone guard and Simasia

Checks whether a drafted reply sounds like Emerson. Like the rest of
[`decision-state-and-tone.md`](decision-state-and-tone.md), it runs through
`response_composer.py` — which means it scores every reply generated in
the dashboard's chat (mode 4 in `README.md`) — plus a set of offline
training/eval scripts. No customer-facing route calls it.

**Simasia is a third-party pip package** (`simasia[urls]==0.3.0`, pinned
0.3.0 as the floor because `pick_best` / `train_from_labeled` don't exist in
0.2.x), not an in-house classifier. It answers one question — "does this
text sound like Emerson, 0 to 1?" — by comparing embeddings. It never calls
an LLM.

## Three layers, deliberately kept separate

The module docstrings in this codebase are explicit about why there are
three separate checks rather than one:

1. **`tone_rules.py`** — regex word-list checks. Catches banned words
   ("holy grail", "game changer"), hedges ("likely", "it depends", "might"),
   and the resolution rule's own tells. Exact, free, instant, and names the
   offending word. These rules were deliberately *removed* from the
   embedding model's job: adding hedge words to a firm sentence moved
   Simasia's score by only 0.023 on average (noise), and in one case the
   score went *up*. The model cannot see single-word hedges.
2. **`tone_guard.py`** — the Simasia wrapper (see below). Compares
   embeddings. Good at ranking candidates against each other, poorly
   calibrated in absolute terms.
3. **`tone_judge.py`** — an LLM call (pinned to `gpt-5` via
   `TONE_JUDGE_MODEL`, deliberately not following `LLM_PROVIDER`, so scores
   stay comparable across runs) that reads the reply *against the plan it
   was given* (depth, structure, decision state) and can catch things
   neither of the others can — e.g. a reply with no banned words, no
   hedges, and a respectable tone score that still never says what's wrong
   with the user's hair.

## What `tone_guard.py` actually does

- Reads `simasia.toml` once (brand id, artifact directory, embedding model)
  so training and scoring can't drift apart.
- Bridges this codebase's key names (`OPENAI_API_KEY` / `OPEN_AI_KEY`) to
  the name Simasia expects (`EMBEDDING_KEY`).
- Loads the trained artifact (`app/simasia_emerson_head.joblib`, gitignored)
  once per process.
- Every read path (`score`, `explain`, `diagnose`, `pick_best`) returns
  `None` / an unranked fallback on any failure — missing model, missing key,
  embedding outage — rather than raising. The docstring is explicit: an
  outage "is not evidence that a reply is off-brand," and callers must
  treat `None` as "no opinion."
- `pick_best(candidates)` is called out as "the reliable way to use
  Simasia": ranking candidates against each other works even while the
  model's absolute scores are poorly calibrated.
- `train_from_feedback()` is the one path that raises on failure instead of
  degrading — a training run that silently did nothing is treated as worse
  than one that stops and says so.

## The measured accuracy problem — read before trusting a score

This is the finding your [[project-tone-system]] memory also captured, now
re-verified against the current code and docstrings:

- Simasia mostly detects "is this hair-care writing," not "is this
  Emerson." Measured: generic curly-hair copy with no brand character
  scored **0.949**; a genuinely on-brand short reply scored **0.588**.
- The first trained model scored 0.543 on unseen text — a coin flip —
  because its bootstrap training data was generated paraphrases, not real
  off-brand examples.
- `tone_judge.py`'s own docstring calls itself "the second judge in this
  codebase" and warns not to repeat the same mistake: run
  `scripts/calibrate_judge.py` and check its verdicts against your own
  reading before gating anything on it.

## Supporting files

- **`tone_registers.py`** — one shared list of off-brand "registers"
  (hedging, generic-assistant, etc.), each with label + guidance text
  written to be pasted directly into a retry prompt. Shared by
  `build_off_brand_corpus.py`, `tone_guard.diagnose()`, and the review
  dashboard, so a category a human reviewer picks and a category the model
  infers are the same string.
- **Training/eval scripts** (`scripts/`): `train_emerson_tone.py` (initial
  training), `build_emerson_simasia_corpus.py` / `build_off_brand_corpus.py`
  (corpus construction), `check_corpus_separation.py`, `calibrate_judge.py`
  (checks `tone_judge.py` against human judgment),
  `evaluate_tone_ranking.py`, `retrain_tone_from_feedback.py` (the path to
  `train_from_feedback()` above).

## Where this connects to the data-collection conversation

The blind-review approve/reject data (see
[`review-tooling.md`](review-tooling.md)) is the real feedback
`retrain_tone_from_feedback.py` needs to move past the synthetic bootstrap
and the 0.543-coin-flip problem. That data already exists in this repo; it
just needs to keep flowing into `train_from_feedback()`.
