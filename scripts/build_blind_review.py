"""Build a blind review page from recorded replies.

Blind matters here. Two instruction versions are being compared, and if the
reviewer can tell which replies are "the new ones" she will mark them up. So the
page carries no version, no batch heading, and no ordering that hints at either:
replies are shuffled with a fixed seed, and the only thing on screen is the
customer's question and the answer.

Nothing is lost by hiding it. Every reply keeps its version in data/reviews/, so
splitting her verdicts by version afterwards is automatic.

Each reply gets an opaque ticket (r1, r2, ...) which is what comes back in the
copied answers. scripts/reviews.py import maps tickets to records.

Usage:
    python scripts/build_blind_review.py --out review.html
    python scripts/build_blind_review.py --versions ed7cedf1db2a 847425ed0fc1
"""

from __future__ import annotations

import argparse
import html
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services import review_store, tone_rules  # noqa: E402

# Plain-English framing of the machine settings. She judges voice, so she gets
# what the customer said and what we decided, never our vocabulary.
SETTINGS = {
    "repair_first": "Her hair is breaking. Rebuild strength before styling anything.",
    "reset_first": "Something is coating her hair and blocking absorption. Clear that first.",
    "climate_control_first": "The Gulf climate is the cause. Seal against humidity rather than adding moisture.",
    "simplify_and_reduce_friction": "She is overwhelmed. Give her one thing to do, not a routine.",
    "balanced_routine_first": "Nothing urgent. Build a sensible routine from her profile.",
}


def _check_glosses(records: list[dict]) -> list[str]:
    """Decision states with no plain-English line. Silence here reaches the expert.

    `SETTINGS.get(decision, decision)` falls back to the raw state name, so a
    missing gloss puts `hold_and_definition_first` on her screen under "What we
    decided" and she reads our vocabulary instead of the decision.
    """
    return sorted({
        state
        for r in records
        if (state := r["selected"].get("decision_state")) and state not in SETTINGS
    })


def build(records: list[dict], seed: int) -> tuple[str, dict[str, str]]:
    # Group by the customer question so she reads all answers to one question
    # together. Within a question, order is shuffled so version cannot be guessed
    # from position.
    by_question: dict[str, list[dict]] = {}
    for r in records:
        by_question.setdefault(r["title"], []).append(r)

    rng = random.Random(seed)
    questions = sorted(by_question)
    rng.shuffle(questions)

    ticket_map: dict[str, str] = {}
    counter = 0
    sections = []

    for index, title in enumerate(questions, start=1):
        group = by_question[title][:]
        rng.shuffle(group)
        first = group[0]

        cards = []
        for position, r in enumerate(group, start=1):
            counter += 1
            ticket = f"r{counter}"
            ticket_map[ticket] = r["id"]
            body = "".join(
                f"<p>{html.escape(p)}</p>" for p in r["reply"].split("\n") if p.strip()
            )
            cards.append(f"""
        <article class="reply" data-id="{ticket}">
          <p class="tag">Answer {position} of {len(group)}</p>
          <div class="reply-body">{body}</div>
          <div class="vote" role="group" aria-label="Rate this answer">
            <button class="btn yes" data-vote="yes" aria-pressed="false">Sounds like us</button>
            <button class="btn no" data-vote="no" aria-pressed="false">Doesn't</button>
            <span class="voted" aria-live="polite"></span>
          </div>
          <div class="say">
            <label for="c-{ticket}">What made you say that? <span>Optional, but the most useful part.</span></label>
            <textarea id="c-{ticket}" rows="2" placeholder="A word or two is plenty. What felt off, or what worked."></textarea>
          </div>
        </article>""")

        decision = first["selected"].get("decision_state", "")
        sections.append(f"""
      <section class="scenario">
        <p class="eyebrow">Question {index} of {len(questions)}</p>
        <h2>{html.escape(title)}</h2>
        <blockquote class="said">{html.escape(first['customer'])}</blockquote>
        <dl class="facts">
          <div><dt>What we decided</dt><dd>{html.escape(SETTINGS.get(decision, decision))}</dd></div>
        </dl>
        <p class="lede">{len(group)} different answers to the same question. Judge each on its own.</p>
        {''.join(cards)}
      </section>""")

    return "".join(sections), ticket_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a blind review page.")
    parser.add_argument("--versions", nargs="*", help="Versions to include. Default: all.")
    parser.add_argument(
        "--scenarios", nargs="*",
        help="Scenarios to include, e.g. --scenarios breakage scalp definition. "
             "Default: all. Rounds are six cards; more than that and she stops reading.",
    )
    parser.add_argument("--out", default="blind_review.html")
    parser.add_argument("--seed", type=int, default=7, help="Shuffle seed, so the page is reproducible.")
    parser.add_argument(
        "--include-rule-breakers", action="store_true",
        help="Send replies that still break a banned-word, hedge or dash rule. Off by default.",
    )
    parser.add_argument(
        "--allow-missing-gloss", action="store_true",
        help="Build even when a decision state has no plain-English line. Off by default: "
             "a raw state name on her screen spends her attention on our vocabulary.",
    )
    args = parser.parse_args()

    import blind_review_template as tpl

    if args.versions:
        records = [r for v in args.versions for r in review_store.load(v)]
    else:
        records = review_store.load_all()

    if args.scenarios:
        wanted = set(args.scenarios)
        unknown = wanted - {r["scenario"] for r in records}
        records = [r for r in records if r["scenario"] in wanted]
        if unknown:
            print(f"\nNo recorded replies for: {', '.join(sorted(unknown))}")
            print("Check the names against evaluate_tone_ranking.SCENARIOS, or run `reviews.py record` first.")

    records = [r for r in records if not r.get("verdict")]
    if not records:
        print("\nNothing unjudged to review.\n")
        return 1

    # Last line of defence. A banned word, a hedge or a dash is detectable for
    # nothing, and her attention is the scarcest thing in this project — she
    # should never spend a card on a failure a regex already found. Generation is
    # supposed to have regenerated these; anything still here got through five
    # tries, which is itself worth knowing.
    if not args.include_rule_breakers:
        clean, dirty = [], []
        for r in records:
            (dirty if tone_rules.check(r["reply"]) else clean).append(r)
        if dirty:
            print(f"\nHolding back {len(dirty)} reply(s) that still break a lexical rule:")
            for r in dirty:
                found = sorted({f for v in tone_rules.check(r["reply"]) for f in v["found"]})
                print(f"  {r['id']}  {', '.join(found)}")
            print("Regenerate them, or pass --include-rule-breakers to send them anyway.")
        records = clean
        if not records:
            print("\nEvery unjudged reply breaks a rule. Nothing to send.\n")
            return 1

    missing = _check_glosses(records)
    if missing:
        print("\nNO PLAIN-ENGLISH LINE FOR: " + ", ".join(missing))
        print("She would read that raw state name under \"What we decided\". Add it to")
        print("SETTINGS in this file, or pass --allow-missing-gloss to build anyway.\n")
        if not args.allow_missing_gloss:
            return 1

    sections, ticket_map = build(records, args.seed)
    questions = len({r["title"] for r in records})

    page = (tpl.HEAD + sections + tpl.FOOT)
    page = page.replace("__TOTAL__", str(len(records))).replace("__QUESTIONS__", str(questions))

    out = Path(args.out)
    out.write_text(page, encoding="utf-8")

    key_path = PROJECT_ROOT / "data" / "reviews" / "_tickets.json"
    key_path.write_text(json.dumps(ticket_map, indent=1), encoding="utf-8")

    by_version: dict[str, int] = {}
    for r in records:
        by_version[r["version"]] = by_version.get(r["version"], 0) + 1

    print(f"\n{len(records)} replies across {questions} questions -> {out}")
    for version, count in sorted(by_version.items()):
        print(f"  {version}  {count} replies")
    print(f"\nTicket map: {key_path.relative_to(PROJECT_ROOT)}")
    print("The page carries no version, no batch label, and no ordering hint.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
