# Emerson tone work — handoff

Everything below was built in one session. Read this before changing anything in
`app/services/decision_state/response_composer.py`.

**Next piece of work, already planned and approved:** per-pipeline testing, built
one pipeline at a time. Plan at
`C:\Users\subar\.claude\plans\whimsical-stargazing-snowflake.md`. Visual map of
the eight pipelines:
https://claude.ai/code/artifact/4ae3a6a5-0ccd-4016-8f38-ebe5021dd88e

**Stage 0 and pipeline 1 (`repair_first`) are done.** The settings bug below is
fixed and `breakage` is recorded and waiting on her.

## The settings migration — read before trusting old `stats` rows

Every tone scenario used to hand-write its `JTEDeliveryPlan`, so each one
reviewed a voice the live pipeline cannot emit. `reset_first` was tested as
troubleshoot/medium/expert_calm where production sends
educate/long/warm_reassuring. The `JTEInput` was junk too, so `readiness_score`
came out 0 every time. `_scenario` now derives the plan from
`jte.resolve_delivery_plan`, the way production does, and all five scenarios
were migrated in one edit.

The `ed7cedf1db2a` vs `847425ed0fc1` comparison still stands: both arms used the
same wrong settings, so the wording test was fair and the revert was right. What
does not stand is **any per-setting row in `reviews.py stats` from the 14
verdicts recorded before this change**. Those replies are labelled with settings
that did not produce them. Read them as wording evidence only, never as
"warm_reassuring does better than expert_calm".

## Where it stands right now

**Reverted to `ed7cedf1db2a` after a blind A/B said the newer wording was worse.**
That is the live wording. `847425ed0fc1` is kept only as a record of what not to do.

The experiment: 16 replies, 4 customer questions, 8 per version, shuffled and
unlabelled, judged by the brand expert.

```
ed7cedf1db2a (old)   5/8 approved
847425ed0fc1 (new)   2/8 approved

               old    new
buildup        1/2    1/2
coated         1/2    1/2
climate        2/2    0/2
frustrated     1/2    0/2
```

**Two things it settled.**

*The change was wrong.* `847425ed0fc1` put a "The Cause" beat at the front of every
structure. Her notes on those replies: "a bit clinical", "too clinical", "generic
AI", "doesn't sound sophisticated". Opening on a cause reads as diagnosis, and
what she praises is teaching: "explains the what and why and then recommends",
"educates and then recommends". **Naming a cause and educating are not the same
move.** The open item "short versus educational" is the real thread here.

*The reasoning behind it was also wrong.* It rested on one chain scoring 2/2 in the
first round. That did not reproduce: the same chain scored 1/2 on a re-run, and
1/2 on a different question through the same chain. Six data points, and the
pattern was noise. Do not build on a result that thin again without reproducing it
first.

## Her concrete asks, not yet done

- **"Your hair isn't the problem" is banned.** The hair is never the problem.
- **"Dubai's hard water" → "the region's".** Default to Dubai only if she says
  Dubai, UAE for any other emirate. One reply used both Dubai and GCC in the same
  breath.
- She would recommend **a reset first** by default when a customer says nothing is
  working. That is prioritisation logic, not wording.

## What was actually wrong, and what fixed it

Almost none of the improvement came from better instructions. It came from
**deleting instructions that contradicted each other.**

- **Six sections were telling the model how to open a reply.** It cannot obey six,
  so it averaged them, and an average of six instructions is a stock phrase. Every
  reply began "I hear your frustration". Reduced to one owner, the opener vanished.
- **The internal notes were written as polished prose, so the model quoted them.**
  `reset_first` said "buildup or a waxy coating" and 5 of 5 replies used that exact
  phrase. Rewritten as clipped notes, it dropped to zero.
- **Length was impossible, not ignored.** Every structure demanded 4 beats while
  `short` allowed 1-3 sentences, plus an unbudgeted empathy sentence. `short` now
  gets 2-beat structures and the prompt states that length wins.
- **The prompt used 20 em-dashes** while telling the model not to. Removed from the
  prompt's own prose first, then instructed.

Run `python scripts/audit_prompt_rules.py` after any edit. It finds rule sets by
inspection, so new blocks are covered automatically, and fails when a concern has
more than two owners.

## What Simasia actually does

Less than the original plan. Measured, it mostly detects **"is this long
explanatory writing about hair"**, not "is this Emerson":

- generic curly-hair copy with no Emerson character: **0.949**
- a genuinely on-brand short reply: **0.588**

It is a reasonable gate (on-brand vs clearly off-brand separates by ~0.69) and a
poor ranker (good replies separate by 0.02-0.09). `pick_best` on several
candidates buys almost nothing. It cannot see single-word hedges at all, which is
why `app/services/tone_rules.py` exists.

The model was retrained on hand-written negatives after the original bootstrap
turned out to score **0.543 on unseen text** — a coin flip. It will only get
genuinely good on real thumbs-down data.

## The layers, and which does what

| layer | catches | cost |
|---|---|---|
| `tone_rules.py` | banned words, hedges, dashes | free, exact |
| `tone_guard.py` (Simasia) | "sounds fine, says nothing" | one embedding call |
| `tone_judge.py` (gpt-5) | vagueness, structure, length vs the plan | one call, ~40s |
| the brand expert | everything that matters | slow, scarce, the only ground truth |

`tone_judge` is audited against 10 known cases and agrees on all 10
(`scripts/calibrate_judge.py`). Do not trust a judge you have not audited — that
is exactly how the Simasia coin flip went unnoticed.

## Model choice

`gpt-4.1`, and deliberately not `gpt-5`. Measured on the composer prompt:

```
gpt-4o    3.8s   quality 3.58   met the length limit 0 times out of 6
gpt-4.1   3.5s   quality 4.45   met it 6 times out of 6
gpt-5    39.7s   quality 4.40   reasoning model, ~1,600 tokens of thinking first
```

`gpt-5` with `reasoning_effort="minimal"` runs at 3.3s and scores 4.5, so it is a
live fallback.

## Still open

1. **The humectant contradiction.** The expert says humectants are good and should
   be balanced with a sealant. `climate_control_first` says *"AVOID:
   humectant-heavy and glycerin-containing formulas in high humidity."* One of
   them is wrong. This is correctness, not voice, and it is the most serious item
   here.
2. **Dramatic personification.** She flagged "escapes by noon" and "your hair is
   fighting you". We removed the empathy formula and the model reached for vivid
   metaphor instead.
3. **Short versus educational.** Both her approvals used the word *educational*
   and her rewrites are longer and explain more. Today's work tightened the length
   limits. Those pull in opposite directions and it is a product decision.
4. **Every customer question is invented.** All four were written by an assistant
   guessing at what Emerson customers say. This is the biggest limitation on
   everything measured here and it does not go away until there are real chat logs.

## Commands

```bash
python scripts/prompt_versions.py -m "why"        # save current wording
python scripts/prompt_versions.py --diff-last     # what changed since last save
python scripts/audit_prompt_rules.py              # find clashing rules
python scripts/reviews.py record                  # generate + save replies
python scripts/reviews.py import answers.txt      # attach expert verdicts
python scripts/reviews.py stats                   # approval rate by setting
python scripts/reviews.py record --scenario breakage --runs 2   # one pipeline only
python scripts/build_blind_review.py --scenarios breakage       # blind review page
python scripts/calibrate_judge.py                 # audit the judge
python -m unittest tests.test_tone_guard          # 55 tests
python -m unittest tests.test_decision_routing    # 24 tests, offline, no LLM
```

Nothing is switched on in production. `compose_response` behaves exactly as it did
unless you pass `candidates` or `tone_floor`.
