"""Replay a real WhatsApp conversation through the pipeline, turn by turn.

Every other test in this project asks the bot one invented question in isolation.
This one drops it into a conversation a human already handled, at the exact points
that human chose to reply, and puts the two answers side by side.

It answers questions no single-turn test can:

  - Does it route somewhere sensible when the customer asks about stock, delivery,
    or whether to try a new brand? Most of a real thread is not a hair problem.
  - Does it ask before recommending, the way the agent did?
  - How long is its answer next to the one the customer actually received?

Assumptions, stated because they change the result
--------------------------------------------------
The export carries no profile and no location. Production reads both from
onboarding, so the replay supplies them:

  profile   the one the customer gives in her own words mid-thread
  env       neutral. With high humidity every turn routes to climate_control_first
            before anything else is considered, which would tell you nothing.

Usage:
    python scripts/replay_whatsapp.py _chat.txt
    python scripts/replay_whatsapp.py _chat.txt --dry-run
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

from app.services.decision_state.decision_engine import build_strategy_payload  # noqa: E402
from app.services.decision_state.jte import resolve_delivery_plan  # noqa: E402
from app.services.decision_state.models import (  # noqa: E402
    EnvironmentalContext, ProfileState, ResponseComposerInput, SessionSignal,
)
from app.services.session_intent.session_intent_service import process_session_intent  # noqa: E402
from app.services.session_signal.signal_detector import SIGNAL_NAMES, detect_signals  # noqa: E402
from enrichment.parse_export import read_export  # noqa: E402

# What the customer states about her own hair, part way through the thread.
PROFILE = ProfileState(
    texture_type="3C", texture_label="Tight Curls",
    porosity="medium", density="medium", elasticity="normal",
    humidity_response="moderate sensitivity", routine_flags=[],
)
ENV = EnvironmentalContext(humidity_level="medium", heat_stress="low", hard_water=False)


def reply_points(turns) -> list[dict]:
    """Each moment the human agent chose to answer, with everything said before it."""
    points, history, pending = [], [], []
    for turn in turns:
        agent = turn.sender.startswith("Emerson")
        if agent:
            if pending:
                points.append({
                    "history": list(history),
                    "customer": [t.text for t in pending],
                    "agent_said": turn.text,
                })
                pending = []
            history.append({"role": "assistant", "content": turn.text})
        else:
            pending.append(turn)
            history.append({"role": "user", "content": turn.text})
    return points


async def collect(rc, prompt, gate, temperature=0.7):
    delay = 8.0
    for attempt in range(6):
        async with gate:
            try:
                return (await rc._collect(prompt, temperature))[0]
            except Exception as exc:  # noqa: BLE001
                if type(exc).__name__ != "RateLimitError" or attempt == 5:
                    raise
        print(f"      rate limited, waiting {delay:.0f}s")
        await asyncio.sleep(delay)
        delay *= 1.5
    return ""


async def run(points, dry_run):
    from app.services.decision_state import response_composer as rc

    gate = asyncio.Semaphore(1)
    delivered: set[str] = set()
    out = []

    for index, point in enumerate(points, 1):
        messages = point["history"]
        said = " / ".join(point["customer"])
        print(f"\n{'=' * 74}\nPOINT {index}\n  customer : {said[:150]}")

        with redirect_stdout(io.StringIO()):
            sigs, intent = await asyncio.gather(
                detect_signals(messages), process_session_intent(messages)
            )
            ss = SessionSignal(**{k: sigs.get(k, False) for k in SessionSignal.model_fields if k in sigs})
            strategy = build_strategy_payload(PROFILE, ss, ENV, intent, frozenset(delivered))
            plan = resolve_delivery_plan(strategy.jte_input, strategy.decision_state)
        delivered.add(strategy.decision_state)

        active = [k for k in SIGNAL_NAMES if sigs.get(k)]
        print(f"  signals  : {active or ['none']}")
        print(f"  intent   : {intent.journey_state} / {intent.confidence_level} / "
              f"{intent.friction_score} / {intent.emotional_state}")
        print(f"  routed   : {strategy.decision_state} -> {plan.response_mode} / "
              f"{plan.response_depth} / {plan.tone_profile} / ask={plan.ask_strategy}")

        record = {
            "point": index, "customer": point["customer"],
            "signals": active, "intent": intent.model_dump(),
            "decision_state": strategy.decision_state, "settings": plan.model_dump(),
            "agent_said": point["agent_said"], "bot_said": None,
        }

        if not dry_run:
            ci = ResponseComposerInput(
                strategy_payload=strategy, jte_delivery_plan=plan, profile_state=PROFILE,
                env=ENV, candidate_products=[], recent_messages=messages,
            )
            record["bot_said"] = (await collect(rc, rc.render_response_prompt(ci), gate)).strip()
            print(f"  human    : {len(point['agent_said']):5d} chars")
            print(f"  bot      : {len(record['bot_said']):5d} chars")

        out.append(record)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a WhatsApp thread through the pipeline.")
    parser.add_argument("export", help="Path to the WhatsApp export.")
    parser.add_argument("--dry-run", action="store_true", help="Route only. No composer calls.")
    parser.add_argument("--limit", type=int, help="Only the first N reply points.")
    args = parser.parse_args()

    turns = read_export(Path(args.export))
    points = reply_points(turns)
    if args.limit:
        points = points[: args.limit]
    print(f"\n{len(turns)} turns, {len(points)} points where the agent replied")

    records = asyncio.run(run(points, args.dry_run))

    if not args.dry_run:
        target = PROJECT_ROOT / "data" / "replays"
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = target / f"replay_{stamp}.json"
        path.write_text(json.dumps({"source": args.export, "points": records}, indent=1,
                                   ensure_ascii=False), encoding="utf-8")
        human = [len(r["agent_said"]) for r in records]
        bot = [len(r["bot_said"]) for r in records if r["bot_said"]]
        print(f"\n{'=' * 74}")
        print(f"saved -> {path.relative_to(PROJECT_ROOT)}")
        if bot:
            print(f"mean length   human {sum(human)//len(human):5d}   bot {sum(bot)//len(bot):5d}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
