"""Generate replies by running the real pipeline from a trigger, and save everything.

The other scripts start from a decision state someone typed in. This one starts
from what a customer said and the context they said it in, then runs the same two
functions production runs:

    build_strategy_payload  ->  which pipeline
    resolve_delivery_plan   ->  which voice

If a case does not route where its `expect_state` says, the run stops before
spending a single LLM call. A reply generated from the wrong pipeline is worse
than no reply: it looks fine and it is answering a different question.

Every run saves three things per reply, which is what makes a verdict readable
later: the trigger that routed it, the exact prompt that produced it, and the
reply itself. Written to data/pipeline_runs/, and recorded into data/reviews/ so
the blind review page picks them up.

Usage:
    python scripts/pipeline_replies.py --list
    python scripts/pipeline_replies.py --state repair_first --runs 6
    python scripts/pipeline_replies.py --case repair_breakage --runs 2
    python scripts/pipeline_replies.py --state repair_first --runs 6 --dry-run

`--dry-run` does the routing check and writes the prompt, with no LLM calls and
no cost. Use it to see what a case will actually ask for before paying for six of
them.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.services import prompt_version, review_store, tone_rules  # noqa: E402
from app.services.decision_state.decision_engine import build_strategy_payload  # noqa: E402
from app.services.decision_state.jte import resolve_delivery_plan  # noqa: E402
from app.services.decision_state.models import ResponseComposerInput  # noqa: E402
from tests.routing_cases import CASES  # noqa: E402

RUNS = PROJECT_ROOT / "data" / "pipeline_runs"


def build_input(case: dict) -> tuple[ResponseComposerInput, str]:
    """Run the real pipeline for one case. Returns the composer input and the state it routed to."""
    with redirect_stdout(io.StringIO()):
        strategy = build_strategy_payload(
            case["profile"], case["expect_signals"], case["env"], case["intent"]
        )
        delivery = resolve_delivery_plan(strategy.jte_input, strategy.decision_state)

    composer_input = ResponseComposerInput(
        strategy_payload=strategy,
        jte_delivery_plan=delivery,
        profile_state=case["profile"],
        env=case["env"],
        candidate_products=[],
        recent_messages=[{"role": "user", "content": case["message"]}],
    )
    return composer_input, strategy.decision_state


async def _collect(rc, prompt: str, temperature: float, gate: asyncio.Semaphore) -> tuple[str, list]:
    """One generation, waiting out the token-per-minute limit rather than dying on it.

    The composer prompt is around 1,800 tokens and a `long` reply adds ~700, so
    six concurrent runs exceed a 30,000 TPM account inside one second. The gate
    caps how many are in flight; the backoff covers the rolling window, which the
    gate alone cannot, because the limit counts the last sixty seconds and not
    the last six calls.
    """
    delay = 8.0
    for attempt in range(6):
        async with gate:
            try:
                return await rc._collect(prompt, temperature)
            except Exception as exc:  # noqa: BLE001 - provider-specific class, matched by name
                if type(exc).__name__ != "RateLimitError" or attempt == 5:
                    raise
        print(f"      rate limited, waiting {delay:.0f}s")
        await asyncio.sleep(delay)
        delay *= 1.5
    return "", []


async def one_reply(rc, prompt: str, temperature: float, attempts: int, gate: asyncio.Semaphore) -> dict:
    """Generate one reply, regenerating while it breaks a lexical rule.

    Lexical rules only. `tone_guard` scores generic hair copy higher than a good
    short reply, and `tone_judge` is the thing being validated against her
    verdicts — filtering by either would choose what she sees using a measure she
    has not agreed to yet.

    A repeat offence escalates: `_retry_prompt` rebuilds from the base prompt, so
    re-sending the same note is the same request again.
    """
    current = prompt
    text, violations = "", []
    seen: set[str] = set()
    used = 0

    for used in range(1, max(1, attempts) + 1):
        text, _usage = await _collect(rc, current, temperature, gate)
        if not text.strip():
            continue
        violations = tone_rules.check(text)
        if not violations:
            break

        guidance = tone_rules.guidance(violations)
        repeats = sorted({f for v in violations for f in v["found"]} & seen)
        if repeats:
            quoted = ", ".join(f'"{f}"' for f in repeats)
            guidance += (
                f"\nA previous draft was already rejected for {quoted} and the rewrite kept "
                f"it. Do not write {quoted} anywhere in the reply, in any position, including "
                "inside brackets or as an aside. Where you would reach for it, use a full stop "
                "and start a new sentence."
            )
        seen.update(f for v in violations for f in v["found"])
        current = rc._retry_prompt(prompt, guidance)

    return {
        "reply": text.strip(),
        "attempts_used": used,
        "violations": [{"category": v["category"], "found": v["found"]} for v in violations],
    }


async def run_case(rc, case: dict, args, version: str, gate: asyncio.Semaphore) -> dict | None:
    composer_input, state = build_input(case)

    print(f"\n{'=' * 74}")
    print(f"CASE  {case['name']}")
    print(f"  trigger  : {case['trigger']}")
    print(f"  customer : {case['message']}")
    print(f"  profile  : {case['profile'].texture_type}, porosity {case['profile'].porosity}, "
          f"elasticity {case['profile'].elasticity}, humidity {case['profile'].humidity_response}")
    print(f"  env      : humidity {case['env'].humidity_level}, hard water {case['env'].hard_water}")

    if state != case["expect_state"]:
        print(f"\n  ROUTING FAILED. expected {case['expect_state']}, got {state}")
        print("  No replies generated. A reply from the wrong pipeline reads fine and")
        print("  answers a different question, which is the one failure worth stopping for.\n")
        return None

    plan = composer_input.jte_delivery_plan
    print(f"  routed to: {state}  ->  {plan.response_mode} / {plan.response_depth} / "
          f"{plan.tone_profile}  (readiness {plan.readiness_band})")

    prompt = rc.render_response_prompt(composer_input)

    record = {
        "case": case["name"],
        "title": case["title"],
        "trigger": case["trigger"],
        "prompt_version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "customer": case["message"],
        "inputs": {
            "profile": case["profile"].model_dump(),
            "env": case["env"].model_dump(),
            "signals": case["expect_signals"].model_dump(),
            "intent": case["intent"].model_dump(),
        },
        "routed_to": state,
        "settings": plan.model_dump(),
        "prompt": prompt,
        "replies": [],
    }

    if args.dry_run:
        print(f"  dry run: prompt is {len(prompt)} chars, no LLM calls made")
        return record

    print(f"  generating {args.runs} reply(s)...")
    results = await asyncio.gather(
        *(one_reply(rc, prompt, args.temperature, args.attempts, gate) for _ in range(args.runs))
    )

    for index, result in enumerate(results, start=1):
        if not result["reply"]:
            print(f"    {index}. empty generation, skipped")
            continue
        record["replies"].append(result)
        rid = review_store.record(
            version=version,
            scenario=case["name"],
            title=case["title"],
            customer=case["message"],
            reply=result["reply"],
            selected=prompt_version.stamp(composer_input)["selected"],
        )
        result["review_id"] = rid
        if result["violations"]:
            faults = "; ".join(f"{v['category']}: {', '.join(v['found'])}" for v in result["violations"])
            print(f"    {index}. {rid}   STILL BREAKS A RULE -> {faults}")
        else:
            print(f"    {index}. {rid}   clean  ({result['attempts_used']} attempt(s), "
                  f"{len(result['reply'])} chars)")

    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate replies through the real pipeline.")
    parser.add_argument("--case", action="append", help="Run this case. Repeatable.")
    parser.add_argument("--state", help="Run every case that routes to this pipeline.")
    parser.add_argument("--runs", type=int, default=2, help="Replies per case.")
    parser.add_argument("--attempts", type=int, default=5,
                        help="Regenerations allowed while a reply still breaks a lexical rule.")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--pause", type=float, default=5, help="Seconds between cases.")
    parser.add_argument("--concurrency", type=int, default=2,
                        help="Generations in flight at once. Above 2 trips a 30k TPM account.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Route and render the prompt, make no LLM calls.")
    parser.add_argument("--list", action="store_true", help="Show every case and exit.")
    args = parser.parse_args()

    if args.list:
        print(f"\n{len(CASES)} case(s):\n")
        for c in CASES:
            print(f"  {c['name']:24s} -> {c['expect_state']:28s} {c['trigger']}")
        print()
        return 0

    chosen = CASES
    if args.state:
        chosen = [c for c in chosen if c["expect_state"] == args.state]
    if args.case:
        wanted = set(args.case)
        unknown = wanted - {c["name"] for c in CASES}
        if unknown:
            print(f"\nNo such case: {', '.join(sorted(unknown))}")
            print(f"Known: {', '.join(c['name'] for c in CASES)}\n")
            return 1
        chosen = [c for c in chosen if c["name"] in wanted]

    if not chosen:
        print("\nNothing selected. Try --list.\n")
        return 1

    from app.services.decision_state import response_composer as rc

    version = prompt_version.version_id()
    calls = 0 if args.dry_run else len(chosen) * args.runs
    print(f"\nPrompt version {version}")
    print(f"{len(chosen)} case(s) x {args.runs} run(s) = {calls} LLM call(s) before retries")
    if not (PROJECT_ROOT / "data" / "prompt_versions" / f"{version}.json").exists():
        print("  WARNING: this version is not saved. Run scripts/prompt_versions.py first,")
        print("  or the wording behind these replies cannot be read back later.")

    async def go() -> list[dict]:
        gate = asyncio.Semaphore(max(1, args.concurrency))
        out = []
        for index, case in enumerate(chosen):
            record = await run_case(rc, case, args, version, gate)
            if record is not None:
                out.append(record)
            if index < len(chosen) - 1:
                await asyncio.sleep(args.pause)
        return out

    records = asyncio.run(go())

    if not records:
        print("\nNothing generated.\n")
        return 1

    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RUNS / f"{version}_{stamp}.json"
    out.write_text(
        json.dumps({"prompt_version": version, "cases": records}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )

    total = sum(len(r["replies"]) for r in records)
    dirty = sum(1 for r in records for reply in r["replies"] if reply["violations"])
    print(f"\n{'=' * 74}")
    print(f"{total} reply(s) saved -> {out.relative_to(PROJECT_ROOT)}")
    print("  each one carries its trigger, its full prompt, and the settings it ran under")
    if dirty:
        print(f"  {dirty} still break a lexical rule. Read those before sending the page.")
    if not args.dry_run:
        names = " ".join(r["case"] for r in records)
        print(f"\nNext:\n  python scripts/build_blind_review.py --scenarios {names} --out review.html")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
