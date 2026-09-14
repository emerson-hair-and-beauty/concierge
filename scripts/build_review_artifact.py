"""Build the review page in the house style, ready to publish as an artifact.

Same job as build_blind_review.py, different output. That one writes a page to
host somewhere; this one writes a single self-contained file that goes straight
up as a Claude artifact, so a round can reach the expert without anyone
deploying anything.

The style is fixed on purpose. She has reviewed on this layout before, and
changing the furniture between rounds costs her attention on the furniture
instead of the replies.

It reuses data/reviews/_tickets.json, so `reviews.py import` reads the pasted
answers back exactly as it always has. Run build_blind_review.py first to write
that map, or pass --seed to shuffle a fresh one.

Usage:
    python scripts/build_review_artifact.py --scenarios repair_breakage repair_low_elasticity
    python scripts/build_review_artifact.py --scenarios repair_breakage --out page.html
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
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.services import review_store, tone_rules  # noqa: E402
from build_blind_review import SETTINGS  # noqa: E402

TICKETS = PROJECT_ROOT / "data" / "reviews" / "_tickets.json"
RUNS = PROJECT_ROOT / "data" / "pipeline_runs"

# Machine settings in her language. She judges voice, so she never reads ours.
TONE_GLOSS = {
    "expert_calm": "Calm and certain",
    "warm_reassuring": "Warm",
    "direct_confident": "Direct",
    "simplified_supportive": "Plain and encouraging",
}
DEPTH_GLOSS = {
    "short": "1 to 3 sentences",
    "medium": "3 to 5 sentences",
    "long": "several short paragraphs",
}


def load_prompts() -> dict[str, dict]:
    """Newest saved prompt and inputs per case, from data/pipeline_runs/."""
    out: dict[str, dict] = {}
    for path in sorted(RUNS.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for case in data.get("cases", []):
            out[case["case"]] = case
    return out


def hair_line(profile: dict) -> str:
    bits = [f"{profile['texture_label']} ({profile['texture_type']})",
            f"{profile['porosity']} porosity",
            f"{profile['density']} density"]
    if profile.get("elasticity"):
        bits.append(f"{profile['elasticity']} elasticity")
    return ", ".join(bits)


def build(records: list[dict], prompts: dict[str, dict], tickets: dict[str, str],
          seed: int | None) -> tuple[str, int, dict[str, str]]:
    by_case: dict[str, list[dict]] = {}
    for r in records:
        by_case.setdefault(r["scenario"], []).append(r)

    if seed is None and tickets:
        # Reuse the existing order so a map already sent out still resolves.
        order = {rid: index for index, rid in enumerate(tickets.values())}
        cases = sorted(by_case, key=lambda c: min(order.get(r["id"], 1e9) for r in by_case[c]))
        for case in cases:
            by_case[case].sort(key=lambda r: order.get(r["id"], 1e9))
        ticket_of = {rid: t for t, rid in tickets.items()}
    else:
        rng = random.Random(seed if seed is not None else 7)
        cases = sorted(by_case)
        rng.shuffle(cases)
        for case in cases:
            rng.shuffle(by_case[case])
        ticket_of = {}
        counter = 0
        for case in cases:
            for r in by_case[case]:
                counter += 1
                ticket_of[r["id"]] = f"r{counter}"

    sections = []
    total = 0

    for index, case in enumerate(cases, start=1):
        group = by_case[case]
        total += len(group)
        source = prompts.get(case)
        first = group[0]
        picks = first["selected"]

        cards = []
        for r in group:
            ticket = ticket_of[r["id"]]
            body = "".join(f"<p>{html.escape(p)}</p>" for p in r["reply"].split("\n") if p.strip())
            cards.append(f"""
        <article class="reply" data-id="{ticket}">
          <div class="reply-body">{body}</div>
          <div class="vote" role="group" aria-label="Rate this reply">
            <button class="btn yes" data-vote="yes" aria-pressed="false">Sounds like us</button>
            <button class="btn no" data-vote="no" aria-pressed="false">Doesn't</button>
            <span class="voted" aria-live="polite"></span>
          </div>
          <div class="say">
            <label for="c-{ticket}">What made you say that? <span>Optional, but the most useful part.</span></label>
            <textarea id="c-{ticket}" rows="2" placeholder="A word or two is plenty. What felt off, or what worked."></textarea>
          </div>
        </article>""")

        hair = hair_line(source["inputs"]["profile"]) if source else "not recorded"
        decided = SETTINGS.get(picks.get("decision_state", ""), picks.get("decision_state", ""))
        sound = (f"{TONE_GLOSS.get(picks.get('tone_profile'), picks.get('tone_profile'))}, "
                 f"{DEPTH_GLOSS.get(picks.get('response_depth'), picks.get('response_depth'))}")

        prompt_block = ""
        if source:
            prompt_block = f"""
        <details class="prompt">
          <summary>See the exact instructions behind these replies</summary>
          <p class="note">The full brief sent to the AI for this conversation. You do not need it to vote, but nothing is hidden.</p>
          <pre>{html.escape(source['prompt'])}</pre>
        </details>"""

        sections.append(f"""
      <section class="scenario">
        <p class="eyebrow">Conversation {index} of {len(cases)}</p>
        <h2>{html.escape(first['title'])}</h2>
        <blockquote class="said">{html.escape(first['customer'])}</blockquote>
        <dl class="facts">
          <div><dt>Her hair</dt><dd>{html.escape(hair)}</dd></div>
          <div><dt>What we decided</dt><dd>{html.escape(decided)}</dd></div>
          <div><dt>How to sound</dt><dd>{html.escape(sound)}</dd></div>
        </dl>
        <p class="lede">{len(group)} replies to the same question. The wording differs each time because each is written fresh, not chosen from a list.</p>
        {''.join(cards)}{prompt_block}
      </section>""")

    return "".join(sections), total, ticket_of


HEAD = """<title>Emerson concierge &mdash; reply review</title>
<style>
  :root{
    /* Mineral, not cream. These replies are about water in hair: hard water,
       humidity, absorption. Neutrals carry a blue bias toward the teal. */
    --ground:#F6F8F8; --raised:#FFFFFF; --ink:#12242A; --muted:#5E7178;
    --rule:#DCE4E5; --accent:#0F7F87; --accent-soft:#E4F0F1; --warm:#B4621C;
    --warm-soft:#F7EBE0; --field:#FBFCFC;
    --serif: Georgia,'Iowan Old Style','Palatino Linotype',Palatino,serif;
    --sans: system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
    --mono: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]){
      --ground:#0D181C; --raised:#132227; --ink:#E4EDEF; --muted:#93A7AE;
      --rule:#25383E; --accent:#3FB3BB; --accent-soft:#14343A; --warm:#DD9152;
      --warm-soft:#3A2A1C; --field:#0F1D22;
    }
  }
  :root[data-theme="dark"]{
    --ground:#0D181C; --raised:#132227; --ink:#E4EDEF; --muted:#93A7AE;
    --rule:#25383E; --accent:#3FB3BB; --accent-soft:#14343A; --warm:#DD9152;
    --warm-soft:#3A2A1C; --field:#0F1D22;
  }
  :root[data-theme="light"]{
    --ground:#F6F8F8; --raised:#FFFFFF; --ink:#12242A; --muted:#5E7178;
    --rule:#DCE4E5; --accent:#0F7F87; --accent-soft:#E4F0F1; --warm:#B4621C;
    --warm-soft:#F7EBE0; --field:#FBFCFC;
  }
  *{box-sizing:border-box}
  body{background:var(--ground);color:var(--ink);font-family:var(--sans);
       line-height:1.6;margin:0;-webkit-font-smoothing:antialiased}
  .wrap{max-width:44rem;margin:0 auto;padding:0 1.5rem 6rem}

  .tally{position:sticky;top:0;z-index:10;background:var(--ground);
         border-bottom:1px solid var(--rule);padding:.7rem 1.5rem;font-size:.8rem}
  .tally-inner{max-width:44rem;margin:0 auto;width:100%;display:flex;
               gap:1rem;align-items:center;justify-content:space-between}
  .count{font-variant-numeric:tabular-nums;color:var(--muted)}
  .count b{color:var(--ink);font-weight:600}
  .copy{font:inherit;font-size:.8rem;border:1px solid var(--rule);background:var(--raised);
        color:var(--ink);padding:.35rem .8rem;border-radius:2px;cursor:pointer}
  .copy:hover{border-color:var(--accent);color:var(--accent)}

  header{padding:4.5rem 0 3rem;border-bottom:1px solid var(--rule);margin-bottom:3.5rem}
  h1{font-family:var(--serif);font-weight:400;font-size:clamp(2rem,5vw,2.9rem);
     line-height:1.15;margin:0 0 1rem;text-wrap:balance;letter-spacing:-.01em}
  .standfirst{font-family:var(--serif);font-size:1.12rem;color:var(--muted);
              margin:0 0 1.6rem;max-width:34rem}
  .ask{border-left:2px solid var(--accent);padding:.1rem 0 .1rem 1.1rem;
       margin:0;font-size:.95rem;max-width:34rem}
  .ask b{color:var(--accent)}

  .eyebrow{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;
           color:var(--accent);margin:0 0 .5rem;font-weight:600}
  .scenario{padding-bottom:3.5rem;margin-bottom:3.5rem;border-bottom:1px solid var(--rule)}
  .scenario:last-of-type{border-bottom:0}
  h2{font-family:var(--serif);font-weight:400;font-size:1.6rem;margin:0 0 1.4rem;
     line-height:1.25;text-wrap:balance}

  .said{font-family:var(--serif);font-size:1.15rem;font-style:italic;
        border-left:2px solid var(--rule);margin:0 0 1.6rem;padding:.2rem 0 .2rem 1.2rem}
  .facts{display:grid;gap:.55rem;margin:0 0 2rem;font-size:.85rem}
  .facts>div{display:grid;grid-template-columns:9.5rem 1fr;gap:1rem}
  dt{color:var(--muted)}
  dd{margin:0}
  @media (max-width:34rem){ .facts>div{grid-template-columns:1fr;gap:.1rem} }

  .lede{font-size:.85rem;color:var(--muted);margin:0 0 1.2rem}
  .stamp{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin:1.6rem 0 0}

  .reply{background:var(--raised);border:1px solid var(--rule);padding:1.5rem;
         margin-bottom:1rem;transition:border-color .15s}
  .reply[data-voted="yes"]{border-color:var(--accent)}
  .reply[data-voted="no"]{border-color:var(--warm)}
  .reply-body{font-family:var(--serif);font-size:1.06rem}
  .reply-body p{margin:0 0 .85rem}
  .reply-body p:last-child{margin-bottom:0}

  .vote{display:flex;gap:.5rem;align-items:center;margin-top:1.3rem;
        padding-top:1.1rem;border-top:1px solid var(--rule);flex-wrap:wrap}
  .btn{font:inherit;font-size:.82rem;border:1px solid var(--rule);background:transparent;
       color:var(--muted);padding:.4rem .9rem;border-radius:2px;cursor:pointer;
       transition:background .15s,color .15s,border-color .15s}
  .btn.yes:hover,.btn.yes[aria-pressed="true"]{background:var(--accent-soft);
       border-color:var(--accent);color:var(--accent)}
  .btn.no:hover,.btn.no[aria-pressed="true"]{background:var(--warm-soft);
       border-color:var(--warm);color:var(--warm)}
  .btn:focus-visible,.copy:focus-visible,summary:focus-visible,textarea:focus-visible{
       outline:2px solid var(--accent);outline-offset:2px}
  .voted{font-size:.78rem;color:var(--muted)}

  /* The comment box is the point of the page, so it is given a tinted well and a
     left rule rather than sitting flush and disappearing into the card. */
  .say{margin-top:1.1rem;display:block;background:var(--field);
       border-left:2px solid var(--accent);padding:.85rem 1rem}
  .say label{display:block;font-size:.8rem;color:var(--ink);margin-bottom:.45rem;font-weight:500}
  .say label span{color:var(--muted);font-weight:400}
  .say textarea{display:block;font:inherit;font-size:.9rem;font-family:var(--sans);
       width:100%;background:var(--raised);color:var(--ink);border:1px solid var(--rule);
       border-radius:2px;padding:.6rem .7rem;resize:vertical;min-height:4rem;line-height:1.5}
  .say textarea::placeholder{color:var(--muted);opacity:.8}
  .say textarea:focus{border-color:var(--accent);outline-offset:0}

  .out{margin-top:2.5rem;border:1px solid var(--accent);background:var(--raised);padding:1.2rem}
  .out-note{margin:0 0 .7rem;font-size:.85rem;color:var(--accent)}
  .out textarea{display:block;width:100%;font-family:var(--mono);font-size:.78rem;
       line-height:1.6;background:var(--field);color:var(--ink);
       border:1px solid var(--rule);border-radius:2px;padding:.8rem;resize:vertical}
  .out textarea:focus{border-color:var(--accent);outline:2px solid var(--accent);outline-offset:1px}
  .out-actions{margin:.9rem 0 0}

  .prompt{margin-top:2rem;border-top:1px solid var(--rule);padding-top:1.2rem}
  summary{cursor:pointer;font-size:.85rem;color:var(--accent);list-style:none}
  summary::-webkit-details-marker{display:none}
  summary::before{content:'+ ';font-family:var(--mono)}
  details[open] summary::before{content:'- '}
  .note{font-size:.8rem;color:var(--muted);margin:.9rem 0 .7rem}
  pre{font-family:var(--mono);font-size:.72rem;line-height:1.55;background:var(--raised);
      border:1px solid var(--rule);padding:1rem;overflow-x:auto;white-space:pre;margin:0}

  footer{margin-top:4rem;padding-top:2rem;border-top:1px solid var(--rule);
         font-size:.85rem;color:var(--muted)}
  footer h3{font-family:var(--serif);font-weight:400;font-size:1.15rem;color:var(--ink);margin:0 0 .7rem}
  @media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<div class="tally">
  <div class="tally-inner">
    <span class="count"><b id="done">0</b> of __TOTAL__ rated &middot; <b id="yes">0</b> yes &middot; <b id="no">0</b> no &middot; <b id="notes">0</b> notes</span>
    <button class="copy" id="copy">Copy my answers</button>
  </div>
</div>

<div class="wrap">
  <header>
    <h1>Does this sound like Emerson?</h1>
    <p class="standfirst">__STANDFIRST__</p>
    <p class="ask">Read each one and answer a single question: <b>would you be happy for a customer to receive this?</b> Ignore typos and length. We are asking about voice. If you can say <em>why</em> in a few words, that is worth more than the vote itself.</p>
    <p class="stamp">Set __VERSION__</p>
  </header>
"""

FOOT = """
  <div class="out">
    <p class="out-note">When you are done, press <b>Copy my answers</b>, then paste it back to us.</p>
    <textarea id="sheet" rows="10" readonly aria-label="Your answers"></textarea>
    <p class="out-actions"><button class="copy" type="button">Copy my answers</button></p>
  </div>

  <footer>
    <h3>What happens to this</h3>
    <p>Every vote is stored against the exact instructions that produced the reply, so
    a note like &ldquo;too clinical&rdquo; can be traced back to the sentence that caused it and
    rewritten. Nothing here is live. No customer has seen any of it.</p>
  </footer>
</div>

<script>
(function(){
  var cards = Array.prototype.slice.call(document.querySelectorAll('.reply'));
  var sheet = document.getElementById('sheet');

  function render(){
    var lines = [], done = 0, yes = 0, no = 0, notes = 0;
    cards.forEach(function(card){
      var id = card.getAttribute('data-id');
      var vote = card.getAttribute('data-voted');
      var note = card.querySelector('textarea').value.trim();
      if (vote === 'yes'){ yes++; done++; }
      else if (vote === 'no'){ no++; done++; }
      if (note) notes++;
      var label = vote === 'yes' ? 'sounds like us'
                : vote === 'no'  ? 'does not sound like us'
                : 'not rated';
      lines.push(id + ': ' + label);
      if (note) lines.push('note: ' + note);
    });
    document.getElementById('done').textContent = done;
    document.getElementById('yes').textContent = yes;
    document.getElementById('no').textContent = no;
    document.getElementById('notes').textContent = notes;
    sheet.value = lines.join('\\n');
  }

  cards.forEach(function(card){
    card.querySelectorAll('.btn').forEach(function(btn){
      btn.addEventListener('click', function(){
        var choice = btn.getAttribute('data-vote');
        var current = card.getAttribute('data-voted');
        var next = current === choice ? null : choice;
        if (next) card.setAttribute('data-voted', next);
        else card.removeAttribute('data-voted');
        card.querySelectorAll('.btn').forEach(function(b){
          b.setAttribute('aria-pressed', String(b.getAttribute('data-vote') === next));
        });
        card.querySelector('.voted').textContent =
          next === 'yes' ? 'Noted' : next === 'no' ? 'Noted' : '';
        render();
      });
    });
    card.querySelector('textarea').addEventListener('input', render);
  });

  // The page runs inside a cross-origin frame, where navigator.clipboard exists
  // but writeText is usually refused. So a rejected promise has to fall through
  // to execCommand rather than reporting failure, and if both refuse, the text
  // is selected on screen so Ctrl+C still works. Never fail silently: she has no
  // way to tell an empty clipboard from a copied one until she pastes.
  function legacyCopy(text){
    var pad = document.createElement('textarea');
    pad.value = text;
    pad.setAttribute('readonly', '');
    pad.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;border:0;padding:0';
    document.body.appendChild(pad);
    var ok = false;
    try {
      pad.focus();
      pad.select();
      pad.setSelectionRange(0, text.length);
      ok = document.execCommand('copy');
    } catch (e) { ok = false; }
    document.body.removeChild(pad);
    return ok;
  }

  function selectSheet(){
    sheet.scrollIntoView({block: 'center', behavior: 'smooth'});
    sheet.removeAttribute('readonly');
    sheet.focus();
    sheet.setSelectionRange(0, sheet.value.length);
    sheet.setAttribute('readonly', '');
  }

  Array.prototype.forEach.call(document.querySelectorAll('.copy'), function(btn){
    var label = btn.textContent;
    btn.addEventListener('click', function(){
      function settle(ok){
        btn.textContent = ok ? 'Copied' : 'Selected below, press Ctrl+C';
        if (!ok) selectSheet();
        setTimeout(function(){ btn.textContent = label; }, ok ? 2200 : 5000);
      }
      if (navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(sheet.value).then(
          function(){ settle(true); },
          function(){ settle(legacyCopy(sheet.value)); }
        );
      } else {
        settle(legacyCopy(sheet.value));
      }
    });
  });

  render();
})();
</script>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the review page in the house style.")
    parser.add_argument("--scenarios", nargs="*", help="Scenarios to include. Default: all unjudged.")
    parser.add_argument("--versions", nargs="*", help="Versions to include. Default: all.")
    parser.add_argument("--out", default="review_artifact.html")
    parser.add_argument("--seed", type=int, default=None,
                        help="Reshuffle and mint a new ticket map instead of reusing the saved one.")
    parser.add_argument("--include-rule-breakers", action="store_true")
    parser.add_argument(
        "--ids", nargs="*",
        help="Build from these exact reply ids, judged or not. For a retest: show her "
             "replies she has already rated, unlabelled, to find out whether her standard "
             "has moved. Writes the ticket map to a separate file so the first verdicts "
             "are never overwritten.",
    )
    args = parser.parse_args()

    retest = bool(args.ids)
    records = ([r for v in args.versions for r in review_store.load(v)]
               if args.versions else review_store.load_all())
    if args.scenarios:
        records = [r for r in records if r["scenario"] in set(args.scenarios)]

    if retest:
        wanted = list(args.ids)
        by_id = {r["id"]: r for r in records}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            print(f"\nNo such reply: {', '.join(missing)}\n")
            return 1
        records = [by_id[i] for i in wanted]
    else:
        records = [r for r in records if not r.get("verdict")]

    if not args.include_rule_breakers:
        held = [r for r in records if tone_rules.check(r["reply"])]
        if held:
            print(f"\nHolding back {len(held)} reply(s) that still break a lexical rule:")
            for r in held:
                found = sorted({f for v in tone_rules.check(r["reply"]) for f in v["found"]})
                print(f"  {r['id']}  {', '.join(found)}")
        records = [r for r in records if not tone_rules.check(r["reply"])]

    if not records:
        print("\nNothing to review.\n")
        return 1

    missing = sorted({r["selected"].get("decision_state") for r in records} - set(SETTINGS))
    if missing and any(missing):
        print(f"\nNo plain-English line for: {', '.join(m for m in missing if m)}")
        print("Add it to SETTINGS in build_blind_review.py first.\n")
        return 1

    # A retest always mints a fresh order. Reusing the saved map would put the
    # replies back in the order she saw them, which is the one hint that would
    # tell her these are repeats.
    tickets = {} if retest else (
        json.loads(TICKETS.read_text(encoding="utf-8")) if TICKETS.exists() else {}
    )
    seed = args.seed if args.seed is not None else (23 if retest else None)
    sections, total, ticket_of = build(records, load_prompts(), tickets, seed)

    versions = sorted({r["version"] for r in records})
    questions = len({r["scenario"] for r in records})
    standfirst = (
        f"{total} replies our concierge wrote to {questions} customer "
        f"{'question' if questions == 1 else 'questions'}. Nothing cherry-picked. Each one was "
        "rewritten until it stopped breaking our own punctuation and word rules, and nothing "
        "else about it was changed."
    )

    page = (HEAD + sections + FOOT)
    page = (page.replace("__TOTAL__", str(total))
                .replace("__STANDFIRST__", html.escape(standfirst))
                .replace("__VERSION__", html.escape(" ".join(versions))))

    out = Path(args.out)
    out.write_text(page, encoding="utf-8")

    key_path = TICKETS.with_name("_tickets_retest.json") if retest else TICKETS
    key_path.write_text(json.dumps({t: rid for rid, t in ticket_of.items()}, indent=1),
                        encoding="utf-8")

    print(f"\n{total} replies across {questions} question(s) -> {out}")
    print(f"Ticket map: {key_path.relative_to(PROJECT_ROOT)}")
    if retest:
        print("\nRETEST. The first verdicts stay in data/reviews/ and are not touched.")
        print("Do NOT run `reviews.py import` on the answers: it would overwrite them.")
        print("\nWhat she said the first time:")
        for rid, ticket in sorted(ticket_of.items(), key=lambda p: int(p[1][1:])):
            first = next(r for r in records if r["id"] == rid)
            # The key is always present and is None until a verdict lands, so a
            # default on .get() never fires.
            print(f"  {ticket}  was {first.get('verdict') or 'unrated':9s}  {rid}")
    else:
        print("Paste her answers back with: python scripts/reviews.py import answers.txt")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
