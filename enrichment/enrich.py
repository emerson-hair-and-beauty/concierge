"""Run one exported conversation all the way to a Klaviyo event.

Nothing is sent until you pass --send. The default prints the exact payload and
stops, because a wrong phone number does not fail loudly. It creates a second
profile for a customer who already has one, and the enrichment lands on the empty
copy. Klaviyo has no undo for that.

Usage:
    python -m enrichment.enrich chat.txt --agent "Emerson Support"
    python -m enrichment.enrich chat.txt --agent "Emerson Support" --phone "+971501234567"
    python -m enrichment.enrich chat.txt --agent "Emerson Support" --send

The agent name is required for a single file. `infer_agent` needs three or more
exports to guess safely, and a wrong guess relabels the customer as the agent and
deletes their words from the detection.

Where the phone number comes from
---------------------------------
The export writes the saved contact name when the agent has the customer in their
phone, and the raw number when they do not. Only the second case gives you the
join key. When the export shows a name, pass --phone yourself.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from enrichment import contacts, klaviyo, parse_export, signal_judge  # noqa: E402
from enrichment.detect import active, detect_once, quiet  # noqa: E402

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

NAME_FLOOR = 0.7


async def analyse(turns: list[dict[str, str]], customer_only: bool, use_judge: bool) -> dict:
    source = parse_export.customer_only(turns) if customer_only else turns
    detector = signal_judge.judge(source) if use_judge else detect_once(source)
    with quiet():
        signals, name = await asyncio.gather(detector, contacts.find_name(turns))
    await asyncio.sleep(0.25)
    return {"signals": signals, "name": name}


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich one WhatsApp export into Klaviyo.")
    parser.add_argument("export", help="Path to the exported .txt chat.")
    parser.add_argument("--agent", required=True,
                        help="The agent's name exactly as it appears in the export.")
    parser.add_argument("--phone", default=None,
                        help="The customer's number in any format. Needed when the export shows a saved name.")
    parser.add_argument("--email", default=None, help="Override the address found in the text.")
    parser.add_argument("--name", default=None,
                        help="Override the name. The export sender is the agent's own label for "
                             "the contact, so it can read 'Mum' or 'Noor DXB'.")
    parser.add_argument("--phrase-list", action="store_true",
                        help="Use the old phrase-matching detector instead of the judge. "
                             "Kept so you can compare the two on the same chat.")
    parser.add_argument("--customer-only", action="store_true",
                        help="Hide the agent's turns from the detector.")
    parser.add_argument("--occurred", default=None,
                        help="ISO timestamp for the event. Defaults to now, which is wrong for an old chat.")
    parser.add_argument("--list", default=os.getenv("KLAVIYO_LIST_ID"),
                        help="Klaviyo list id to add the profile to. Defaults to KLAVIYO_LIST_ID. "
                             "Find it in Klaviyo under Audience > Lists & Segments; it is the short "
                             "code in the list URL.")
    parser.add_argument("--send", action="store_true",
                        help="Actually write to Klaviyo. Without this, the payloads are only printed.")
    args = parser.parse_args()

    path = Path(args.export)
    if not path.is_file():
        print(f"\nNo file at {path}\n")
        return 1

    turns = parse_export.read_export(path)
    if not turns:
        print(f"\nParsed {path.name} and found no messages. Check the export format by hand.\n")
        return 1

    senders = {t.sender for t in turns}
    if args.agent not in senders:
        print(f"\n--agent {args.agent!r} does not appear in this export.")
        print(f"Senders found: {', '.join(sorted(senders))}\n")
        return 1

    customer_senders = sorted(senders - {args.agent})
    mapped = parse_export.to_turns(turns, args.agent)

    print(f"\n{path.name}")
    print(f"  {len(turns)} turns, customer: {', '.join(customer_senders) or '(none)'}")

    result = asyncio.run(analyse(mapped, args.customer_only, not args.phrase_list))
    signals = sorted(active(result["signals"]))
    by_layer = result["signals"].get("by_layer", {})

    # ---- identity ------------------------------------------------------
    # A sender written as "~Kety" is the name the CUSTOMER chose, because the
    # contact is not saved in the agent's phone and WhatsApp fell back to their
    # profile name. That is the same value the live webhook returns as
    # `value.contacts[0].profile.name`, so it is safe to write to a profile.
    #
    # A sender with no tilde is the agent's own label for that contact. It reads
    # "Mum" or "Noor DXB" as often as a real first name. It is still used, but it
    # is called out below, and --name overrides it.
    profile_names = {t.sender for t in turns if t.is_profile_name}
    sender_name = next((s for s in customer_senders if not klaviyo.looks_like_phone(s)), None)
    name_is_theirs = sender_name in profile_names
    model_name = result["name"]
    use_name = args.name or sender_name
    if not use_name and model_name["name"] and model_name["confidence"] >= NAME_FLOOR:
        use_name = model_name["name"]

    phone_source = "--phone" if args.phone else "export sender"
    raw_phone = args.phone or next((s for s in customer_senders if klaviyo.looks_like_phone(s)), None)
    phone = klaviyo.normalise_phone(raw_phone)
    email = args.email or contacts.pick_email(mapped)
    missed = contacts.count_obfuscated(mapped)

    evidence = result["signals"].get("evidence", {})
    reasons = result["signals"].get("reasons", {})
    print(f"\n  method       {'phrase list' if args.phrase_list else 'judge'}")
    print(f"  signals      {', '.join(signals) or '(none)'}")
    if args.phrase_list:
        # Only the phrase-list path has two layers. The judge reads once and
        # gives a reason per signal instead, which says more than a layer name.
        print(f"    matched    {', '.join(by_layer.get('primary', [])) or '-'}")
        print(f"    inferred   {', '.join(by_layer.get('fallback', [])) or '-'}")
    if signals:
        print("\n  what the customer said for each one")
        for signal in signals:
            quote = evidence.get(signal)
            shown = f'"{quote}"' if quote else "(no quote returned)"
            print(f"    {signal:20s} {shown}")
            if reasons.get(signal):
                print(f"    {'':20s} {reasons[signal][:100]}")
        # Two signals quoting one sentence is the taxonomy double-counting, not
        # the customer having two problems. The judge has explicit absent clauses
        # for the buildup_present and scalp_sensitivity pair, so this should be
        # rare now. It stays as the check that tells you if that stops holding.
        quotes = [q for q in (evidence.get(s) for s in signals) if q]
        if len(quotes) != len(set(quotes)):
            print("\n  ! two signals quote the same words. That is one complaint counted twice.")
    print(f"  email        {email or '(none found)'}"
          + (f"   [{missed} written-out address(es) the pattern cannot read]" if missed else ""))
    print(f"  name         {use_name or '(none)'}")
    print(f"    sender     {sender_name or '(the export shows a number)'}"
          + ("   [their own profile name]" if name_is_theirs
             else "   [the agent's saved label - check it is a real name]" if sender_name
             else ""))
    print(f"    model      {model_name['name'] or '(none)'} "
          f"(confidence {model_name['confidence']:.2f})")
    print(f"  phone        {phone or '(none)'}   from {phone_source if raw_phone else 'nowhere'}")

    if raw_phone and not phone:
        print(f"\n  ! {raw_phone!r} does not look like a phone number, so it was dropped.")

    # ---- guard ---------------------------------------------------------
    blocked = klaviyo.check_identity(phone, email)
    if blocked:
        print(f"\n  STOP: {blocked}\n")
        return 1

    if not signals:
        print("\n  No signals found. Nothing worth writing to a profile.\n")
        return 0

    occurred = None
    if args.occurred:
        try:
            occurred = datetime.fromisoformat(args.occurred)
        except ValueError:
            print(f"\n  --occurred {args.occurred!r} is not an ISO timestamp.\n")
            return 1

    profile_payload = klaviyo.build_profile(
        signals, phone=phone, email=email, name=use_name, updated_at=occurred
    )
    event_payload = klaviyo.build_event(
        signals,
        phone=phone,
        email=email,
        name=use_name,
        by_layer=by_layer,
        confidence=result["signals"].get("confidence_score", 0.0),
        evidence=evidence,
        method="phrase_list" if args.phrase_list else "judge",
        conversation_id=path.stem,
        occurred_at=occurred,
    )

    print("\n" + "=" * 68)
    print("PAYLOADS" + ("" if args.send else "  (not sent - pass --send to write them)"))
    print("=" * 68)
    print("\n1. profile-import")
    print(json.dumps(profile_payload, indent=2))
    print(f"\n2. add to list: {args.list or '(no --list given, this step is skipped)'}")
    print("\n3. events")
    print(json.dumps(event_payload, indent=2))

    if not args.send:
        print("\n  Read the identifiers above before you send. If that email or phone does not")
        print("  already exist in Klaviyo, step 1 creates a new profile.\n")
        return 0

    # Profile first. It is the only call that returns an id, and the list call
    # needs one. A failure here stops the rest, because a list membership and an
    # event with no profile behind them are worse than nothing.
    print("\nSending to Klaviyo...")
    try:
        response = klaviyo.upsert_profile(profile_payload)
    except Exception as e:
        print(f"  1. profile-import FAILED: {e}\n")
        return 1
    if response.status_code not in (200, 201):
        print(f"  1. profile-import {response.status_code}: {response.text[:400]}\n")
        return 1

    profile_id = klaviyo.profile_id_from(response)
    created = response.status_code == 201
    print(f"  1. profile-import {response.status_code} "
          f"({'created a NEW profile' if created else 'updated an existing profile'}), "
          f"id {profile_id}")
    if created:
        print("     A new profile means nothing matched this email or phone. Check that this")
        print("     is what you expected before you run it on more conversations.")

    failed = False
    if args.list and profile_id:
        try:
            response = klaviyo.add_to_list(args.list, profile_id)
            ok = response.status_code == 204
            print(f"  2. add to list {response.status_code}"
                  + ("" if ok else f": {response.text[:300]}"))
            failed = failed or not ok
        except Exception as e:
            print(f"  2. add to list FAILED: {e}")
            failed = True
    else:
        print("  2. add to list skipped (no --list given)")

    try:
        response = klaviyo.send_event(event_payload)
        ok = response.status_code == 202
        print(f"  3. events {response.status_code}"
              + ("" if ok else f": {response.text[:300]}"))
        failed = failed or not ok
    except Exception as e:
        print(f"  3. events FAILED: {e}")
        failed = True

    print("\n  A 2xx means Klaviyo accepted the write. It is not proof the data landed on")
    print("  the person you meant. Open the profile in Klaviyo and read it.\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
