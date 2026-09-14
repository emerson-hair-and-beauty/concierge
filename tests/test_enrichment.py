"""Tests for the WhatsApp enrichment package.

Everything here runs offline. No test makes a model call, so these check the
wiring — parsing, role mapping, email selection — and not detection quality.
Detection quality is a measurement, and `python -m enrichment.compare` is where
it gets measured against real conversations.
"""

import unittest

from enrichment import contacts, detect, klaviyo, parse_export

ANDROID = """\
17/08/2026, 14:30 - Messages and calls are end-to-end encrypted. No one outside of this chat can read them.
17/08/2026, 14:32 - Sarah: my hair is so dry
17/08/2026, 14:32 - Sarah: and itchy
17/08/2026, 14:33 - Emerson Support: how long has that been going on?
17/08/2026, 14:35 - Sarah: weeks now
it started after I changed shampoo
17/08/2026, 14:36 - Sarah: <Media omitted>
17/08/2026, 14:40 - Sarah: my email is sarah.k@example.com if you need it
"""

IOS = """\
[17/08/2026, 2:32:05 PM] Sarah: my hair is so dry
[17/08/2026, 2:33:10 PM] Emerson Support: how long has that been going on?
"""


class ParseExport(unittest.TestCase):
    def test_reads_android_format(self):
        turns = parse_export.parse_text(ANDROID)
        self.assertEqual(turns[0].sender, "Sarah")
        self.assertEqual(turns[0].text, "my hair is so dry")

    def test_reads_ios_format(self):
        turns = parse_export.parse_text(IOS)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[1].sender, "Emerson Support")

    def test_drops_the_encryption_notice(self):
        # A system line is not something a customer said. Left in, it becomes a
        # turn and the model analyses WhatsApp's own boilerplate.
        turns = parse_export.parse_text(ANDROID)
        self.assertFalse(any("encrypted" in t.text for t in turns))

    def test_joins_a_message_that_runs_over_lines(self):
        # "it started after I changed shampoo" carries the cause. Split from its
        # first line it loses the subject and the signal goes with it.
        turns = parse_export.parse_text(ANDROID)
        multi = [t for t in turns if t.text.startswith("weeks now")]
        self.assertEqual(len(multi), 1)
        self.assertIn("changed shampoo", multi[0].text)

    def test_drops_media_placeholders(self):
        # "<Media omitted>" says a photo existed. It says nothing about hair, so
        # it must not reach the detector as a customer statement.
        turns = parse_export.parse_text(ANDROID)
        self.assertFalse(any("omitted" in t.text.lower() for t in turns))

    def test_infers_the_agent_from_who_appears_everywhere(self):
        # The agent is in every chat. Each customer is in one. Without this the
        # comparison cannot tell the two sides apart.
        exports = {
            f"chat_{i}": parse_export.parse_text(
                f"17/08/2026, 14:32 - Customer{i}: hello\n"
                f"17/08/2026, 14:33 - Emerson Support: hi there\n"
            )
            for i in range(4)
        }
        self.assertEqual(parse_export.infer_agent(exports), "Emerson Support")

    def test_refuses_to_infer_the_agent_from_too_few_files(self):
        # A wrong guess silently relabels the customer as the agent and removes
        # their words from detection. Two files cannot support the guess.
        exports = {
            "a": parse_export.parse_text("17/08/2026, 14:32 - Sarah: hello\n"),
            "b": parse_export.parse_text("17/08/2026, 14:32 - Sarah: hello\n"),
        }
        self.assertIsNone(parse_export.infer_agent(exports))

    def test_strips_the_tilde_from_an_unsaved_contact(self):
        # WhatsApp writes "~Kety" when the contact is not saved. Left alone, the
        # tilde reaches Klaviyo as the customer's first name.
        turns = parse_export.parse_text("17/08/2026, 14:32 - ~Kety: my hair is dry\n")
        self.assertEqual(turns[0].sender, "Kety")

    def test_records_that_the_name_came_from_their_own_profile(self):
        # The tilde is the only thing that tells a name the CUSTOMER chose from a
        # label the AGENT typed. Without it we cannot tell "Kety" from "Mum", and
        # one of those must never be written to a profile.
        theirs = parse_export.parse_text("17/08/2026, 14:32 - ~Kety: hello\n")
        label = parse_export.parse_text("17/08/2026, 14:32 - Mum: hello\n")
        self.assertTrue(theirs[0].is_profile_name)
        self.assertFalse(label[0].is_profile_name)

    def test_matches_an_agent_name_that_contains_an_ampersand(self):
        # Real business names are not tidy. "Emerson Hair & Beauty" must match.
        turns = parse_export.parse_text(
            "17/08/2026, 14:33 - Emerson Hair & Beauty: how can we help?\n"
        )
        self.assertEqual(turns[0].sender, "Emerson Hair & Beauty")

    def test_maps_the_agent_to_assistant(self):
        turns = parse_export.parse_text(ANDROID)
        mapped = parse_export.to_turns(turns, "Emerson Support")
        roles = {t["content"]: t["role"] for t in mapped}
        self.assertEqual(roles["my hair is so dry"], "user")
        self.assertEqual(roles["how long has that been going on?"], "assistant")

    def test_customer_only_removes_the_agent(self):
        mapped = parse_export.to_turns(parse_export.parse_text(ANDROID), "Emerson Support")
        self.assertTrue(all(t["role"] == "user" for t in parse_export.customer_only(mapped)))


class Contacts(unittest.TestCase):
    def test_finds_the_email_the_customer_typed(self):
        mapped = parse_export.to_turns(parse_export.parse_text(ANDROID), "Emerson Support")
        self.assertEqual(contacts.pick_email(mapped), "sarah.k@example.com")

    def test_ignores_an_address_the_agent_typed(self):
        # The agent's own signature address would otherwise become the customer's
        # email, and every profile would collapse onto one address.
        turns = [
            {"role": "assistant", "content": "reach us at support@emerson.example"},
            {"role": "user", "content": "thanks"},
        ]
        self.assertIsNone(contacts.pick_email(turns))

    def test_keeps_the_last_address_not_the_first(self):
        # A customer who mistypes an address types it again. The correction is
        # the one that counts.
        turns = [
            {"role": "user", "content": "sarah@gmial.example"},
            {"role": "user", "content": "sorry, sarah@gmail.example"},
        ]
        self.assertEqual(contacts.pick_email(turns), "sarah@gmail.example")

    def test_strips_trailing_punctuation(self):
        turns = [{"role": "user", "content": "it is sarah@example.com."}]
        self.assertEqual(contacts.pick_email(turns), "sarah@example.com")

    def test_counts_written_out_addresses_without_storing_them(self):
        # The count decides whether writing a parser is worth it. It must never
        # produce an address, because a guessed address reaches a real person.
        turns = [{"role": "user", "content": "its sarah at gmail dot com"}]
        self.assertEqual(contacts.count_obfuscated(turns), 1)
        self.assertIsNone(contacts.pick_email(turns))


class DetectWiring(unittest.TestCase):
    def test_still_reaches_the_names_it_borrows(self):
        # detect.py imports private names from signal_detector so that app/ stays
        # untouched and the six signal definitions live in one file. A rename
        # there breaks this package, and this test is the thing that says so.
        from app.services.session_signal import signal_detector

        for name in ("_DETECTION_PROMPT", "_FALLBACK_PROMPT", "SIGNAL_NAMES", "detect_signals"):
            self.assertTrue(hasattr(signal_detector, name), f"signal_detector.{name} is gone")

    def test_asks_for_the_evidence_the_prompts_never_request(self):
        # Neither prompt in signal_detector specifies an output shape, so the
        # evidence_quote it reads back is almost always empty. This package adds
        # the request. If the wording is lost, the report goes back to printing
        # six bare labels that prove nothing.
        self.assertIn("evidence", detect._EVIDENCE_FORMAT)
        self.assertIn("CUSTOMER only", detect._EVIDENCE_FORMAT)

    def test_merge_keeps_a_signal_found_by_either_layer(self):
        # The fallback layer exists to catch what the matching layer misses.
        # Merging with AND, or letting the last result win, would discard it.
        primary = {"absorption_blocked": True, "hold_loss": False}
        fallback = {"absorption_blocked": False, "hold_loss": True}
        merged = detect._merge(primary, fallback)
        self.assertTrue(merged["absorption_blocked"])
        self.assertTrue(merged["hold_loss"])
        self.assertFalse(merged["breakage_active"])

    def test_merge_keeps_the_evidence_key_present(self):
        # enrich.py reads result["evidence"] unconditionally. An empty result
        # missing the key would crash the report instead of printing "no quote".
        self.assertEqual(detect._empty()["evidence"], {})

    def test_window_matches_the_chat_pipeline(self):
        # process_session_signals sends messages[-10:]. If this drifts, the
        # per-message mode stops measuring production and measures a variation.
        self.assertEqual(detect.CHAT_WINDOW, 10)


class Klaviyo(unittest.TestCase):
    def test_adds_the_plus_that_whatsapp_omits(self):
        # wa_id arrives as "971501234567". Klaviyo matches on "+971501234567".
        # Without the plus, no profile matches and a duplicate one is created.
        self.assertEqual(klaviyo.normalise_phone("971501234567"), "+971501234567")

    def test_strips_the_formatting_a_person_types(self):
        self.assertEqual(klaviyo.normalise_phone("+971 (50) 123-4567"), "+971501234567")

    def test_refuses_a_number_that_cannot_be_real(self):
        # A guess here writes to the wrong person's profile. Returning None costs
        # one skipped enrichment; guessing costs a real customer's data.
        self.assertIsNone(klaviyo.normalise_phone("12345"))
        self.assertIsNone(klaviyo.normalise_phone("1234567890123456789"))
        self.assertIsNone(klaviyo.normalise_phone(""))
        self.assertIsNone(klaviyo.normalise_phone(None))

    def test_tells_a_saved_name_from_a_raw_number(self):
        # The export shows the saved contact name, or the number when the contact
        # is not saved. Only the number can join to a Klaviyo profile.
        self.assertTrue(klaviyo.looks_like_phone("+971 50 123 4567"))
        self.assertFalse(klaviyo.looks_like_phone("Sarah"))
        self.assertFalse(klaviyo.looks_like_phone("Emerson Support"))

    def test_refuses_to_send_without_any_identifier(self):
        # This is the guard that stops an unjoinable profile being created. A
        # profile with no email and no phone can never be matched to anyone.
        self.assertIsNotNone(klaviyo.check_identity(None, None))
        self.assertIsNone(klaviyo.check_identity("+971501234567", None))
        self.assertIsNone(klaviyo.check_identity(None, "sarah@example.com"))

    def test_omits_identifiers_it_does_not_have(self):
        # Sending "phone_number": null makes Klaviyo reject the whole event.
        payload = klaviyo.build_event(["hold_loss"], phone=None, email="s@example.com", name=None)
        profile = payload["data"]["attributes"]["profile"]["data"]["attributes"]
        self.assertNotIn("phone_number", profile)
        self.assertNotIn("first_name", profile)
        self.assertEqual(profile["email"], "s@example.com")

    def test_keeps_the_two_layers_apart_in_the_properties(self):
        # The matching layer quotes the customer. The fallback layer infers. A
        # segment built only on inferred signals deserves a second look, and it
        # cannot get one if both are flattened into a single list.
        payload = klaviyo.build_event(
            ["hold_loss", "breakage_active"],
            phone="+971501234567", email=None, name="Sarah",
            by_layer={"primary": ["hold_loss"], "fallback": ["breakage_active"]},
        )
        props = payload["data"]["attributes"]["properties"]
        self.assertEqual(props["matched_signals"], ["Curls lose definition"])
        self.assertEqual(props["inferred_signals"], ["Breakage"])
        self.assertEqual(props["signal_set"], klaviyo.SIGNAL_SET_VERSION)

    def test_profile_reads_as_english_not_as_identifiers(self):
        # A marketer opening this profile in Klaviyo must not meet
        # "buildup_present". They cannot act on an identifier, and they should
        # not have to ask an engineer what it means.
        payload = klaviyo.build_profile(
            ["buildup_present", "scalp_sensitivity"],
            phone="+971501234567", email=None, name="Kety",
        )
        props = payload["data"]["attributes"]["properties"]
        self.assertEqual(props["Hair Concerns"], ["Product buildup", "Scalp sensitivity"])
        self.assertEqual(set(props), {"Hair Concerns", "Hair Concerns Updated"})

    def test_concerns_stay_a_list_not_a_joined_string(self):
        # Klaviyo segments a list with "contains" on whole values. Joined into
        # one string, selecting "Breakage" would also match anything else that
        # happens to contain the word.
        payload = klaviyo.build_profile(
            ["breakage_active"], phone="+971501234567", email=None, name=None
        )
        self.assertIsInstance(payload["data"]["attributes"]["properties"]["Hair Concerns"], list)

    def test_updated_is_a_date_not_a_microsecond_timestamp(self):
        # Nobody segments on the second a support chat was read, and
        # "2026-08-19T11:49:35.352344+00:00" is unreadable on a profile.
        payload = klaviyo.build_profile(
            ["hold_loss"], phone="+971501234567", email=None, name=None
        )
        stamp = payload["data"]["attributes"]["properties"]["Hair Concerns Updated"]
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}$")

    def test_the_version_stamp_stays_off_the_profile(self):
        # signal_set is plumbing. It belongs on the event, which is the audit
        # record, not on the profile a person reads every day.
        payload = klaviyo.build_profile(
            ["hold_loss"], phone="+971501234567", email=None, name=None
        )
        self.assertNotIn("whatsapp_signal_set", payload["data"]["attributes"]["properties"])
        event = klaviyo.build_event(["hold_loss"], phone="+971501234567", email=None, name=None)
        self.assertEqual(event["data"]["attributes"]["properties"]["signal_set"],
                         klaviyo.SIGNAL_SET_VERSION)

    def test_list_add_uses_the_relationship_shape(self):
        # The list endpoint takes an array of profile references, not a profile
        # object. The wrong shape returns 400 and adds nobody.
        payload = klaviyo.build_list_add("01H8ABCDEF")
        self.assertEqual(payload, {"data": [{"type": "profile", "id": "01H8ABCDEF"}]})

    def test_reads_the_profile_id_out_of_the_response(self):
        # Step 2 cannot run without this id, and only step 1 returns one.
        class FakeResponse:
            def json(self):
                return {"data": {"type": "profile", "id": "01H8ABCDEF"}}

        self.assertEqual(klaviyo.profile_id_from(FakeResponse()), "01H8ABCDEF")

    def test_survives_a_response_that_carries_no_id(self):
        # An error body has no data.id. Raising here would hide the real status
        # code behind a KeyError.
        class FakeResponse:
            def json(self):
                return {"errors": [{"detail": "invalid phone number"}]}

        self.assertIsNone(klaviyo.profile_id_from(FakeResponse()))

    def test_carries_the_quote_behind_each_signal(self):
        # Kety's hold_loss quote said her wash and go lasts a week, which is the
        # opposite of hold loss. Only the quote makes that visible. A label with
        # no evidence cannot be checked by anyone.
        payload = klaviyo.build_event(
            ["hold_loss"], phone="+971501234567", email=None, name=None,
            evidence={"hold_loss": "my wash and go lasts a week"},
        )
        props = payload["data"]["attributes"]["properties"]
        self.assertEqual(props["evidence"]["Curls lose definition"],
                         "my wash and go lasts a week")

    def test_trims_a_long_quote(self):
        # A quote is a check on one label, not a copy of the conversation. The
        # less of a private support chat that reaches Klaviyo, the better.
        payload = klaviyo.build_event(
            ["hold_loss"], phone="+971501234567", email=None, name=None,
            evidence={"hold_loss": "x" * 900},
        )
        quote = payload["data"]["attributes"]["properties"]["evidence"]["Curls lose definition"]
        self.assertEqual(len(quote), klaviyo.MAX_QUOTE)

    def test_keeps_the_quotes_off_the_profile(self):
        # A profile property can be read into an email template. These are the
        # customer's own words about an inflamed scalp, so they must not sit
        # anywhere a template can reach.
        payload = klaviyo.build_profile(
            ["scalp_sensitivity"], phone="+971501234567", email=None, name="Kety"
        )
        self.assertNotIn("evidence", payload["data"]["attributes"]["properties"])

    def test_carries_a_conversation_id_for_repeat_runs(self):
        # Klaviyo deduplicates nothing. Running the same export twice doubles the
        # history unless something on the event says which conversation it was.
        payload = klaviyo.build_event(
            ["hold_loss"], phone="+971501234567", email=None, name=None,
            conversation_id="chat_sarah",
        )
        self.assertEqual(
            payload["data"]["attributes"]["properties"]["conversation_id"], "chat_sarah"
        )


if __name__ == "__main__":
    unittest.main()
