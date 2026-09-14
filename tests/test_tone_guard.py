"""Tests for the Emerson tone guardrail and the ranked composition path.

Everything here runs offline. The embedder is a deterministic stub, so these
tests exercise our wiring — degradation, ranking, usage accounting — rather than
the quality of any trained model.
"""

import asyncio
import pathlib
import sys
import tempfile
import unittest

import numpy as np

from app.services import prompt_version, tone_guard, tone_judge, tone_registers, tone_rules
from app.services.decision_state import response_composer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import retrain_tone_from_feedback as retrain  # noqa: E402


class KeywordEmbedder:
    """Deterministic offline embedding backend: warm/friendly vs stiff/corporate."""

    def encode(self, sentences, **_kwargs):
        vectors = []
        for sentence in sentences:
            text = sentence.lower()
            friendly = sum(w in text for w in ("hey", "curls", "wash day", "here's"))
            formal = sum(w in text for w in ("kindly", "advised", "processing", "inquiry"))
            vectors.append([friendly, formal, len(text.split()) / 100])
        return np.asarray(vectors, dtype=np.float32)


ON_BRAND = (
    "Hey, here's how to refresh day-2 curls. Wash day does not have to be complicated. "
    "Here's what is happening with your curls. Hey, wash day is the place to start. "
    "Your curls need this on wash day. Here's the fix for limp curls."
)
OFF_BRAND = (
    "Kindly be advised your inquiry is processing. Kindly await further review. "
    "Your inquiry is processing and will be advised. Kindly note the processing delay. "
    "Please be advised your inquiry requires processing. Kindly resubmit your inquiry."
)


def trained_guard(artifact_dir):
    from simasia import SimasiaGuard

    guard = SimasiaGuard(
        brand_id="emerson_test",
        artifact_dir=artifact_dir,
        embedding_model=KeywordEmbedder(),
    )
    guard.train(ON_BRAND, OFF_BRAND)
    return guard


class ToneGuardDegradationTests(unittest.TestCase):
    """With no trained model, every read path must return 'no opinion' — never
    raise, and never report a low score, which would be a lie about the text."""

    def setUp(self):
        tone_guard.reset_cache()
        # Simulate "no model on disk" without depending on whether one exists.
        tone_guard._load_attempted = True
        tone_guard._guard = None

    def tearDown(self):
        tone_guard.reset_cache()

    def test_score_and_explain_return_none(self):
        self.assertIsNone(tone_guard.score("Hey, here's the fix for your curls."))
        self.assertIsNone(tone_guard.explain("Hey, here's the fix for your curls."))

    def test_pick_best_ships_first_candidate_unguarded(self):
        result = tone_guard.pick_best(["first reply", "second reply"])
        self.assertEqual(result["text"], "first reply")
        self.assertFalse(result["guarded"])
        self.assertIsNone(result["score"])

    def test_pick_best_tolerates_empty_and_blank_input(self):
        self.assertEqual(tone_guard.pick_best([])["text"], "")
        self.assertEqual(tone_guard.pick_best(["  ", ""])["text"], "")

    def test_train_from_feedback_raises_rather_than_no_opping(self):
        with self.assertRaises(RuntimeError):
            tone_guard.train_from_feedback([("some reply", 1)])


class ToneGuardRankingTests(unittest.TestCase):
    def setUp(self):
        tone_guard.reset_cache()

    def tearDown(self):
        tone_guard.reset_cache()

    def _install(self, guard):
        tone_guard._load_attempted = True
        tone_guard._guard = guard

    def test_picks_the_on_brand_candidate(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            self._install(trained_guard(artifact_dir))

            result = tone_guard.pick_best([
                "Kindly be advised your inquiry is processing.",
                "Hey, here's how to refresh day-2 curls on wash day.",
            ])

        self.assertEqual(result["text"], "Hey, here's how to refresh day-2 curls on wash day.")
        self.assertTrue(result["guarded"])
        self.assertIsNotNone(result["score"])
        self.assertEqual(len(result["ranked"]), 2)

    def test_single_candidate_skips_the_embedding_call(self):
        class ExplodingGuard:
            def pick_best(self, candidates):
                raise AssertionError("pick_best must not be called for one candidate")

        self._install(ExplodingGuard())
        result = tone_guard.pick_best(["only reply"])

        self.assertEqual(result["text"], "only reply")
        self.assertFalse(result["guarded"])

    def test_embedding_outage_degrades_to_first_candidate(self):
        class FailingGuard:
            def pick_best(self, candidates):
                raise ConnectionError("embedding endpoint unreachable")

        self._install(FailingGuard())
        result = tone_guard.pick_best(["first reply", "second reply"])

        self.assertEqual(result["text"], "first reply")
        self.assertFalse(result["guarded"])


class RankedCompositionTests(unittest.TestCase):
    """The composer's candidates>1 path: N parallel generations, one ranked reply."""

    def setUp(self):
        tone_guard.reset_cache()
        self._real_run_llm_agent = response_composer.run_llm_agent

    def tearDown(self):
        response_composer.run_llm_agent = self._real_run_llm_agent
        tone_guard.reset_cache()

    def _stub_llm(self, replies):
        """Yield a different scripted reply per call, with token usage."""
        calls = {"n": 0}

        async def fake_run_llm_agent(prompt, temperature=0.1, **_kwargs):
            index = calls["n"]
            calls["n"] += 1
            self.assertGreater(temperature, 0.1, "ranking must sample above the 0.1 default")
            yield {"type": "content", "content": replies[index % len(replies)]}
            yield {
                "type": "token_usage",
                "model": "test-model",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

        response_composer.run_llm_agent = fake_run_llm_agent
        return calls

    def _drain(self, prompt, candidates):
        async def run():
            return [c async for c in response_composer._compose_ranked(prompt, candidates, 0.1)]

        return asyncio.run(run())

    def test_ships_the_on_brand_candidate_and_sums_usage(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            tone_guard._load_attempted = True
            tone_guard._guard = trained_guard(artifact_dir)

            self._stub_llm([
                "Kindly be advised your inquiry is processing.",
                "Hey, here's how to refresh day-2 curls on wash day.",
            ])
            chunks = self._drain("prompt", candidates=2)

        content = [c for c in chunks if c["type"] == "content"]
        usage = [c for c in chunks if c["type"] == "token_usage"]
        tone = [c for c in chunks if c["type"] == "tone"]

        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]["content"], "Hey, here's how to refresh day-2 curls on wash day.")

        # Two generations happened, so the caller must be billed for both.
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0]["usage"]["total_tokens"], 30)

        self.assertEqual(len(tone), 1)
        self.assertTrue(tone[0]["guarded"])
        self.assertEqual(tone[0]["candidates"], 2)

    def test_reply_still_ships_when_the_tone_model_is_unavailable(self):
        tone_guard._load_attempted = True
        tone_guard._guard = None

        self._stub_llm(["first reply", "second reply"])
        chunks = self._drain("prompt", candidates=2)

        content = [c for c in chunks if c["type"] == "content"]
        tone = [c for c in chunks if c["type"] == "tone"]

        self.assertEqual(content[0]["content"], "first reply")
        self.assertFalse(tone[0]["guarded"])
        self.assertIsNone(tone[0]["score"])

    def test_one_failed_generation_does_not_sink_the_reply(self):
        tone_guard._load_attempted = True
        tone_guard._guard = None
        calls = {"n": 0}

        async def flaky(prompt, temperature=0.1, **_kwargs):
            index = calls["n"]
            calls["n"] += 1
            if index == 0:
                raise ConnectionError("provider dropped the stream")
            yield {"type": "content", "content": "surviving reply"}

        response_composer.run_llm_agent = flaky
        chunks = self._drain("prompt", candidates=2)

        content = [c for c in chunks if c["type"] == "content"]
        self.assertEqual(content[0]["content"], "surviving reply")

    def test_all_generations_failing_raises(self):
        async def always_fails(prompt, temperature=0.1, **_kwargs):
            raise ConnectionError("provider down")
            yield  # pragma: no cover - makes this an async generator

        response_composer.run_llm_agent = always_fails
        with self.assertRaises(ConnectionError):
            self._drain("prompt", candidates=2)


class UsageMergeTests(unittest.TestCase):
    def test_groups_by_model(self):
        merged = response_composer._merged_usage([
            {"model": "a", "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
            {"model": "a", "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9}},
            {"model": "b", "usage": {"prompt_tokens": 7, "completion_tokens": 0, "total_tokens": 7}},
        ])
        by_model = {c["model"]: c["usage"] for c in merged}

        self.assertEqual(by_model["a"]["total_tokens"], 12)
        self.assertEqual(by_model["b"]["total_tokens"], 7)

    def test_no_usage_reported_yields_nothing(self):
        self.assertEqual(response_composer._merged_usage([]), [])


class FeedbackLogTests(unittest.TestCase):
    """Parsing of the dashboard's append-only feedback_log.jsonl."""

    LONG_A = "Here is what is happening with your curls on wash day and how to fix the buildup."
    LONG_B = (
        "Kindly be advised that your inquiry regarding the aforementioned item is "
        "currently undergoing processing and a further review will follow shortly."
    )

    def _log(self, rows):
        """Write rows to a temp log. Dicts are encoded; raw strings pass through
        verbatim so tests can include malformed lines."""
        import json
        import os

        handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
        for row in rows:
            handle.write((json.dumps(row) if isinstance(row, dict) else row) + "\n")
        handle.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        return pathlib.Path(handle.name)

    def _load(self, rows, min_words=15):
        return retrain.load_examples(self._log(rows), min_words)

    def test_maps_ratings_to_labels(self):
        examples, _ = self._load([
            {"response": self.LONG_A, "rating": "positive"},
            {"response": self.LONG_B, "rating": "negative"},
        ])
        self.assertEqual(dict(examples), {self.LONG_A: 1, self.LONG_B: 0})

    def test_a_changed_mind_does_not_train_both_sides(self):
        """The log is append-only, so the same text can carry two verdicts."""
        examples, _ = self._load([
            {"response": self.LONG_A, "rating": "positive"},
            {"response": self.LONG_A, "rating": "negative"},
        ])
        self.assertEqual(examples, [(self.LONG_A, 0)])

    def test_unusable_rows_are_counted_not_crashed_on(self):
        examples, skipped = self._load([
            {"response": self.LONG_A, "rating": "positive"},
            {"response": "", "rating": "positive"},
            {"response": "far too short", "rating": "positive"},
            {"response": self.LONG_B, "rating": "unclear"},
            "{ not json",
        ])
        self.assertEqual(examples, [(self.LONG_A, 1)])
        self.assertEqual(skipped["empty response"], 1)
        self.assertEqual(skipped["under 15 words"], 1)
        self.assertEqual(skipped["no usable rating"], 1)
        self.assertEqual(skipped["malformed json"], 1)

    def test_blank_lines_are_ignored(self):
        examples, skipped = self._load(["", "   ", {"response": self.LONG_A, "rating": "positive"}])
        self.assertEqual(len(examples), 1)
        self.assertEqual(sum(skipped.values()), 0)


class ToneFloorTests(unittest.TestCase):
    """compose_response(tone_floor=...): generate one, retry only if it falls short."""

    def setUp(self):
        tone_guard.reset_cache()
        self._real = response_composer.run_llm_agent

    def tearDown(self):
        response_composer.run_llm_agent = self._real
        tone_guard.reset_cache()

    def _stub(self, replies):
        calls = {"n": 0, "prompts": []}

        async def fake(prompt, temperature=0.1, **_kwargs):
            i = calls["n"]
            calls["n"] += 1
            calls["prompts"].append(prompt)
            yield {"type": "content", "content": replies[min(i, len(replies) - 1)]}
            yield {
                "type": "token_usage",
                "model": "m",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

        response_composer.run_llm_agent = fake
        return calls

    def _scores(self, mapping):
        """Install a guard whose score depends on the text it is given."""

        class ScriptedGuard:
            def explain(self, text):
                return {
                    "score": mapping[text],
                    "closest_off_brand": {"text": tone_registers.EXAMPLES["hedging"][0]},
                }

            def evaluate_response(self, text):
                return mapping[text]

        tone_guard._load_attempted = True
        tone_guard._guard = ScriptedGuard()

    def _drain(self, floor, attempts=2):
        async def run():
            return [
                c
                async for c in response_composer._compose_with_floor("BASE", 0.1, floor, attempts)
            ]

        return asyncio.run(run())

    def test_passing_reply_costs_one_generation(self):
        calls = self._stub(["good reply"])
        self._scores({"good reply": 0.9})
        chunks = self._drain(floor=0.7)

        self.assertEqual(calls["n"], 1, "a passing reply must not trigger a retry")
        tone = [c for c in chunks if c["type"] == "tone"][0]
        self.assertEqual(tone["attempts"], 1)
        self.assertTrue(tone["passed"])

    def test_weak_reply_is_retried_with_named_feedback(self):
        calls = self._stub(["weak reply", "better reply"])
        self._scores({"weak reply": 0.3, "better reply": 0.9})
        chunks = self._drain(floor=0.7)

        self.assertEqual(calls["n"], 2)
        self.assertEqual([c for c in chunks if c["type"] == "content"][0]["content"], "better reply")

        retry_prompt = calls["prompts"][1]
        self.assertIn("REVISION REQUIRED", retry_prompt)
        self.assertIn("unresolved", retry_prompt, "should carry the hedging guidance")

    def test_off_brand_example_is_never_shown_to_the_model(self):
        """Pasting the bad example into the prompt invites it to be echoed back."""
        calls = self._stub(["weak reply", "better reply"])
        self._scores({"weak reply": 0.3, "better reply": 0.9})
        self._drain(floor=0.7)

        self.assertNotIn("Frizz can happen for a lot", calls["prompts"][1])

    def test_ships_the_best_attempt_not_the_last(self):
        calls = self._stub(["first reply", "worse reply"])
        self._scores({"first reply": 0.6, "worse reply": 0.1})
        chunks = self._drain(floor=0.9)

        self.assertEqual(calls["n"], 2)
        self.assertEqual([c for c in chunks if c["type"] == "content"][0]["content"], "first reply")
        tone = [c for c in chunks if c["type"] == "tone"][0]
        self.assertFalse(tone["passed"], "neither attempt cleared the floor")

    def test_usage_covers_every_attempt(self):
        self._stub(["weak reply", "better reply"])
        self._scores({"weak reply": 0.3, "better reply": 0.9})
        chunks = self._drain(floor=0.7)

        usage = [c for c in chunks if c["type"] == "token_usage"][0]
        self.assertEqual(usage["usage"]["total_tokens"], 30)

    def test_without_a_tone_model_it_generates_once_and_ships(self):
        calls = self._stub(["only reply"])
        tone_guard._load_attempted = True
        tone_guard._guard = None
        chunks = self._drain(floor=0.7)

        self.assertEqual(calls["n"], 1, "no model means no scoring and no retry")
        self.assertEqual([c for c in chunks if c["type"] == "content"][0]["content"], "only reply")
        tone = [c for c in chunks if c["type"] == "tone"][0]
        self.assertFalse(tone["guarded"])
        self.assertIsNone(tone["score"])


class RegisterClassifierTests(unittest.TestCase):
    def test_every_example_maps_back_to_its_own_register(self):
        for name, examples in tone_registers.EXAMPLES.items():
            for text in examples:
                self.assertEqual(tone_registers.classify(text), name, text[:50])

    def test_unknown_text_falls_back_to_generic_guidance(self):
        self.assertIsNone(tone_registers.classify("a wholly unrelated sentence about bicycles"))
        self.assertIn("authority", tone_registers.guidance_for(None))

    def test_every_register_has_actionable_guidance(self):
        for name, meta in tone_registers.REGISTERS.items():
            self.assertIn(name, tone_registers.EXAMPLES, f"{name} has no training examples")
            self.assertGreater(len(meta["guidance"]), 80, f"{name} guidance is too vague to act on")


class ToneRuleTests(unittest.TestCase):
    """Word-list rules — the checks the embedding model provably cannot make.

    Measured on the trained model, adding hedge words to a firm sentence moved the
    score by 0.023 on average and in one case raised it, while "likely" cleared a
    0.85 floor in live output. These rules exist to close exactly that gap.
    """

    def _found(self, text):
        return sorted(f for v in tone_rules.check(text) for f in v["found"])

    def test_catches_the_single_word_hedge_the_model_missed(self):
        text = "Your high porosity hair is likely absorbing too much moisture."
        self.assertEqual(self._found(text), ["likely"])

    def test_removing_the_hedge_clears_it(self):
        self.assertEqual(tone_rules.check("Your high porosity hair is absorbing too much moisture."), [])

    def test_soft_hedge_counts_when_it_is_about_the_reader(self):
        self.assertIn("may", self._found("Your hair may be struggling with buildup."))

    def test_soft_hedge_is_allowed_when_teaching_generally(self):
        """Emerson's own blog uses "may" in 3.6% of chunks; flagging that as
        off-brand would call the brand's own voice a violation."""
        self.assertEqual(tone_rules.check("Curly gels may contain film-forming polymers."), [])

    def test_strict_hedge_counts_even_without_addressing_the_reader(self):
        self.assertIn("it depends", self._found("It depends on the porosity of the strand."))

    def test_catches_banned_hype_and_sales_language(self):
        self.assertEqual(self._found("This is amazing, a total game changer."), ["amazing", "game changer"])
        self.assertEqual(self._found("You need to buy it, results are guaranteed."), ["guaranteed", "you need to"])

    def test_catches_the_unspaced_em_dash(self):
        """The form that slipped past the spaced-only rule, taken from real output."""
        text = "When the balance tips too far toward moisture—especially in high porosity hair—it snaps."
        self.assertEqual(self._found(text), ["—"])

    def test_catches_the_spaced_dash_too(self):
        self.assertEqual(self._found("Protein rebuilds the shaft — moisture alone will not."), ["—"])

    def test_numeric_range_is_not_a_dash_violation(self):
        """"2–3 days" is a range. Flagging it would make the rule unusable in copy
        that quotes a frequency, which repair and reset routines always do."""
        self.assertEqual(tone_rules.check("Use it once a week for 2–3 weeks."), [])

    def test_catches_internal_profile_labels_read_aloud(self):
        """Taken from real output after the "bind every action to a reason" edit.
        Asked to justify an action, the model quoted the profile block at her."""
        text = "With medium fragility and high definition difficulty, your hair struggles."
        self.assertEqual(self._found(text), ["high definition difficulty", "medium fragility"])

    def test_the_plain_word_is_still_allowed(self):
        """"Fragility" is ordinary English. Only the label-and-value form is ours."""
        self.assertEqual(tone_rules.check("Softened to the point of fragility, it snaps."), [])

    def test_clean_emerson_copy_passes(self):
        text = (
            "Your definition drops by midday because humidity swells the cuticle and lifts "
            "the curl pattern apart. Switch to a glycerin-free styler and seal it."
        )
        self.assertEqual(tone_rules.check(text), [])

    def test_guidance_names_the_offending_words(self):
        violations = tone_rules.check("Your hair is likely dry and this is amazing.")
        guidance = tone_rules.guidance(violations)
        self.assertIn('"likely"', guidance)
        self.assertIn('"amazing"', guidance)

    def test_violations_fail_the_floor_regardless_of_score(self):
        """A high-scoring reply that breaks a stated rule must still be retried."""

        class GenerousGuard:
            def explain(self, text):
                return {"score": 0.99, "closest_off_brand": {"text": "irrelevant"}}

            def evaluate_response(self, text):
                return 0.99

        tone_guard.reset_cache()
        tone_guard._load_attempted = True
        tone_guard._guard = GenerousGuard()
        self.addCleanup(tone_guard.reset_cache)

        real = response_composer.run_llm_agent
        self.addCleanup(lambda: setattr(response_composer, "run_llm_agent", real))
        calls = {"n": 0}

        async def fake(prompt, temperature=0.1, **_kwargs):
            calls["n"] += 1
            yield {
                "type": "content",
                "content": "Your hair is likely dry." if calls["n"] == 1 else "Your hair is dry.",
            }

        response_composer.run_llm_agent = fake

        async def run():
            return [c async for c in response_composer._compose_with_floor("BASE", 0.1, 0.5, 2)]

        chunks = asyncio.run(run())

        self.assertEqual(calls["n"], 2, "0.99 score must not excuse a banned word")
        self.assertEqual([c for c in chunks if c["type"] == "content"][0]["content"], "Your hair is dry.")
        tone = [c for c in chunks if c["type"] == "tone"][0]
        self.assertTrue(tone["passed"])
        self.assertEqual(tone["violations"], [])


class ToneJudgeTests(unittest.TestCase):
    """The reading judge. Offline: the model call is stubbed."""

    def _stub(self, payload):
        import json as _json

        class Msg:
            content = _json.dumps(payload)

        class Choice:
            message = Msg()

        class Resp:
            choices = [Choice()]

        class Completions:
            def create(self, **_kw):
                return Resp()

        class Chat:
            completions = Completions()

        class Client:
            chat = Chat()

        return Client()

    def _run(self, payload, reply="a reply with some substance to it"):
        import openai

        real = openai.OpenAI
        openai.OpenAI = lambda **_kw: self._stub(payload)
        self.addCleanup(lambda: setattr(openai, "OpenAI", real))
        return tone_judge.judge(reply, {"required length": "1-3 sentences"})

    def test_reports_average_and_lowest(self):
        v = self._run({
            "scores": {
                "names_cause": {"score": 5, "reason": "names buildup"},
                "follows_depth": {"score": 1, "reason": "eight sentences"},
                "sounds_emerson": {"score": 3, "reason": "fine"},
            },
            "worst_problem": "too long",
        })
        self.assertEqual(v["average"], 3.0)
        self.assertEqual(v["lowest"], 1, "one bad criterion must stay visible behind the average")
        self.assertEqual(v["worst_problem"], "too long")

    def test_a_single_failure_is_not_hidden_by_a_good_average(self):
        """Five good scores and one failure still averages respectably, which is
        why `lowest` is reported alongside it."""
        v = self._run({
            "scores": {f"c{i}": {"score": 5, "reason": "good"} for i in range(5)}
            | {"stays_grounded": {"score": 1, "reason": "invented a growth claim"}}
        })
        self.assertGreater(v["average"], 4)
        self.assertEqual(v["lowest"], 1)

    def test_empty_reply_is_not_sent_to_the_model(self):
        self.assertIsNone(tone_judge.judge("   ", {}))

    def test_model_failure_degrades_to_none(self):
        import openai

        real = openai.OpenAI

        def boom(**_kw):
            raise ConnectionError("judge unreachable")

        openai.OpenAI = boom
        self.addCleanup(lambda: setattr(openai, "OpenAI", real))
        self.assertIsNone(tone_judge.judge("a reply", {}))

    def test_unparseable_verdict_degrades_to_none(self):
        self.assertIsNone(self._run({"scores": {}}))

    def test_every_criterion_defines_how_it_fails(self):
        """A criterion without a stated failure mode gets judged on vibes."""
        for name, c in tone_judge.CRITERIA.items():
            self.assertIn("question", c, name)
            self.assertGreater(len(c["fails_when"]), 60, f"{name} needs a concrete failure mode")

    def test_plan_carries_what_the_writer_was_told(self):
        import evaluate_tone_ranking as ev

        plan = tone_judge.plan_from_composer_input(ev.SCENARIOS["frustrated"])
        self.assertIn("sentence", plan["required length"].lower())
        self.assertEqual(plan["decision state"], "simplify_and_reduce_friction")
        self.assertIn("cut it all off", plan["customer said"])


class PromptVersionTests(unittest.TestCase):
    """Version ids for the composer's instructions. Offline and free."""

    def test_same_wording_gives_the_same_id(self):
        self.assertEqual(prompt_version.version_id(), prompt_version.version_id())

    def test_changing_one_word_changes_the_id(self):
        parts = prompt_version.collect()
        before = prompt_version.version_id(parts)
        parts["tables"]["depth_instructions"]["short"] += " Keep it tight."
        self.assertNotEqual(before, prompt_version.version_id(parts))

    def test_key_order_does_not_affect_the_id(self):
        """Otherwise a harmless reordering would look like a wording change."""
        parts = prompt_version.collect()
        before = prompt_version.version_id(parts)
        parts["blocks"] = dict(reversed(list(parts["blocks"].items())))
        self.assertEqual(before, prompt_version.version_id(parts))

    def test_it_finds_the_real_instruction_blocks(self):
        parts = prompt_version.collect()
        self.assertIn("voice_block", parts["blocks"])
        self.assertIn("tone_instructions", parts["tables"])
        self.assertIn("decision_explanations", parts["tables"])

    def test_templates_are_tracked_separately_from_instructions(self):
        """Templates carry {placeholders} and are scaffolding; keeping them apart
        stops a template edit from drowning a diff in noise."""
        parts = prompt_version.collect()
        self.assertIn("composer_prompt", parts["templates"])
        self.assertNotIn("composer_prompt", parts["blocks"])

    def test_diff_names_the_exact_option_that_changed(self):
        older = prompt_version.collect()
        newer = prompt_version.collect()
        newer["tables"]["tone_instructions"]["warm_reassuring"] = "something else entirely"
        changes = prompt_version.diff(older, newer)
        self.assertEqual(changes["changed"], ["tone_instructions:warm_reassuring"])
        self.assertEqual(changes["added"], [])
        self.assertEqual(changes["removed"], [])

    def test_diff_reports_a_removed_option(self):
        older = prompt_version.collect()
        newer = prompt_version.collect()
        del newer["tables"]["depth_instructions"]["long"]
        self.assertIn("depth_instructions:long", prompt_version.diff(older, newer)["removed"])

    def test_stamp_records_the_settings_that_were_chosen(self):
        """A rejected reply needs both the wording in force and the options picked:
        an instruction can be badly written, or fine but wrongly selected."""
        import evaluate_tone_ranking as ev

        stamp = prompt_version.stamp(ev.SCENARIOS["frustrated"])
        self.assertEqual(stamp["prompt_version"], prompt_version.version_id())
        self.assertEqual(stamp["selected"]["decision_state"], "simplify_and_reduce_friction")
        self.assertEqual(stamp["selected"]["response_depth"], "short")

    def test_snapshot_is_self_contained(self):
        """A saved version must carry the full text, not references to it. The
        whole point is reading back what an instruction said months later, after
        the composer has moved on."""
        snap = prompt_version.snapshot("why this exists")
        self.assertEqual(snap["note"], "why this exists")
        self.assertGreater(snap["counts"]["options"], 20)

        flat = prompt_version.flatten(snap)
        self.assertIn("block:voice_block", flat)
        self.assertEqual(flat["block:voice_block"], response_composer._VOICE_BLOCK)
        self.assertEqual(
            flat["decision_explanations:reset_first"],
            response_composer._DECISION_EXPLANATIONS["reset_first"],
        )

    def test_a_snapshot_survives_a_round_trip_through_json(self):
        """Versions are stored as JSON on disk, so the id must be stable across it."""
        import json as _json

        snap = prompt_version.snapshot()
        restored = _json.loads(_json.dumps(snap, ensure_ascii=False))
        self.assertEqual(prompt_version.diff(snap, restored),
                         {"added": [], "removed": [], "changed": []})


if __name__ == "__main__":
    unittest.main()
