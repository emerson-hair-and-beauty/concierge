"""One call versus two: does splitting substance from voice produce better replies?

The idea under test
-------------------
The single-call prompt hands one model about a dozen rule sets and asks it to
satisfy all of them at once. An audit of that file found four separate
instructions about how to open a reply and five restatements of the resolution
rule. A model that cannot obey every instruction averages them, and an average of
several instructions reads as a formula.

The two-call version splits the work. The first call sees the diagnosis and none
of the voice rules; the second sees the voice rules and none of the diagnosis.
Neither has to average anything.

What this measures
------------------
Both arms answer the same scenarios and are scored by the same judge, so the
comparison is like for like. Three things decide it:

  quality   the judge's average across six criteria
  facts     whether the voice pass silently changed what the draft said. This is
            the specific way chaining fails, and a quality score will not catch
            it: a reply can read beautifully and recommend the wrong thing.
  cost      two calls, so roughly double the latency and spend. The gain has to
            be worth that.

Every reply, draft, and score is written out in full. Read them. The numbers say
which arm won on average; only the text tells you whether you would ship it.

Usage:
    python scripts/compare_chained.py
    python scripts/compare_chained.py --runs 3 --out results.md
"""

from __future__ import annotations

import argparse
import asyncio
import re
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_tone_ranking import SCENARIOS  # noqa: E402

from app.services import tone_judge, tone_rules  # noqa: E402
from app.services.decision_state import response_composer as rc  # noqa: E402

_STOPWORDS = {
    "the", "and", "your", "you", "that", "this", "with", "for", "are", "not", "but", "its",
    "it", "is", "to", "of", "a", "in", "on", "so", "if", "as", "at", "be", "by", "or", "an",
}


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOPWORDS}


def _fact_drift(draft: str, final: str) -> float:
    """How much of the draft's substance survived the rewrite, 0 to 1.

    Crude on purpose: a share of meaningful words kept. It will not catch a
    reversed recommendation, which is why the full text is printed for reading.
    A sharp drop means the voice pass rewrote more than the wording.
    """
    a, b = _content_words(draft), _content_words(final)
    return len(a & b) / len(a) if a else 1.0


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()])


async def run_single(ci, temperature: float) -> dict:
    started = time.monotonic()
    text, _ = await rc._collect(rc.render_response_prompt(ci), temperature)
    return {"text": text, "draft": None, "seconds": time.monotonic() - started}


async def run_chained(ci, temperature: float) -> dict:
    started = time.monotonic()
    result = await rc.compose_chained(ci, temperature)
    return {"text": result["text"], "draft": result["draft"], "seconds": time.monotonic() - started}


def score(entry: dict, ci) -> dict:
    verdict = tone_judge.judge(entry["text"], tone_judge.plan_from_composer_input(ci))
    entry["verdict"] = verdict
    entry["sentences"] = _sentences(entry["text"])
    entry["violations"] = [f for v in tone_rules.check(entry["text"]) for f in v["found"]]
    entry["kept"] = _fact_drift(entry["draft"], entry["text"]) if entry["draft"] else None
    return entry


def _report(rows: list[tuple[str, str, dict]], out: Path) -> None:
    lines = ["# One call vs two calls", ""]

    for arm in ("single", "chained"):
        picked = [r for r in rows if r[1] == arm and r[2].get("verdict")]
        if not picked:
            continue
        avg = statistics.mean(r[2]["verdict"]["average"] for r in picked)
        low = statistics.mean(r[2]["verdict"]["lowest"] for r in picked)
        sec = statistics.mean(r[2]["seconds"] for r in picked)
        vio = sum(len(r[2]["violations"]) for r in picked)
        lines.append(f"**{arm}** quality {avg:.2f} | worst criterion {low:.1f} | {sec:.1f}s | {vio} rule breaks")
        if arm == "chained":
            kept = [r[2]["kept"] for r in picked if r[2]["kept"] is not None]
            if kept:
                lines.append(f"  facts kept through the rewrite: {statistics.mean(kept)*100:.0f}%")
    lines.append("")

    criteria = list(tone_judge.CRITERIA)
    lines += ["## Scores by criterion", "", "| arm | " + " | ".join(criteria) + " |",
              "|---" * (len(criteria) + 1) + "|"]
    for arm in ("single", "chained"):
        picked = [r for r in rows if r[1] == arm and r[2].get("verdict")]
        if not picked:
            continue
        cells = []
        for c in criteria:
            vals = [r[2]["verdict"]["scores"].get(c, {}).get("score") for r in picked]
            vals = [v for v in vals if isinstance(v, (int, float))]
            cells.append(f"{statistics.mean(vals):.1f}" if vals else "-")
        lines.append(f"| {arm} | " + " | ".join(cells) + " |")
    lines.append("")

    lines += ["## Every reply", ""]
    for scenario in sorted({r[0] for r in rows}):
        lines.append(f"### {scenario}")
        said = SCENARIOS[scenario].recent_messages[-1]["content"]
        lines.append(f"> customer: {said}")
        lines.append("")
        for name, arm, e in [r for r in rows if r[0] == scenario]:
            v = e.get("verdict")
            head = f"**{arm}** — {e['sentences']} sentences, {e['seconds']:.1f}s"
            if v:
                head += f", quality {v['average']}"
            if e["violations"]:
                head += f", rule breaks: {e['violations']}"
            if e["kept"] is not None:
                head += f", facts kept {e['kept']*100:.0f}%"
            lines += [head, ""]
            if e["draft"]:
                lines += ["<details><summary>draft from call 1</summary>", "",
                          "> " + e["draft"].strip().replace("\n", "\n> "), "", "</details>", ""]
            lines += ["> " + e["text"].strip().replace("\n", "\n> "), ""]
            if v:
                for c, s in v["scores"].items():
                    lines.append(f"- `{c}` **{s.get('score')}** — {s.get('reason','')}")
                lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


async def main_async(args) -> int:
    rows: list[tuple[str, str, dict]] = []

    for scenario, ci in SCENARIOS.items():
        for _ in range(args.runs):
            for arm, runner in (("single", run_single), ("chained", run_chained)):
                entry = await runner(ci, args.temperature)
                rows.append((scenario, arm, score(entry, ci)))
            await asyncio.sleep(args.pause)

    out = PROJECT_ROOT / args.out
    _report(rows, out)

    print()
    for arm in ("single", "chained"):
        picked = [r for r in rows if r[1] == arm and r[2].get("verdict")]
        if not picked:
            continue
        avg = statistics.mean(r[2]["verdict"]["average"] for r in picked)
        sec = statistics.mean(r[2]["seconds"] for r in picked)
        vio = sum(len(r[2]["violations"]) for r in picked)
        extra = ""
        kept = [r[2]["kept"] for r in picked if r[2]["kept"] is not None]
        if kept:
            extra = f"   facts kept {statistics.mean(kept)*100:.0f}%"
        print(f"  {arm:8s} quality {avg:.2f}   {sec:.1f}s   {vio} rule breaks{extra}")
    print(f"\nFull replies and per-criterion reasons: {out}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare one-call and two-call composition.")
    parser.add_argument("--runs", type=int, default=2, help="Replies per scenario per arm.")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--pause", type=float, default=12, help="Seconds between rounds, for rate limits.")
    parser.add_argument("--out", default="chained_comparison.md")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
