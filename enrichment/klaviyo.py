"""Build and send the Klaviyo event that carries the signals.

Why an event and not profile properties
---------------------------------------
A property overwrites. Set `last_signal = "hold_loss"` and you lose the fact that
the same customer reported breakage a month ago. An event keeps the history, and
Klaviyo can still build a segment from it: "has WhatsApp Signal Detected where
signal equals breakage_active at least once over all time".

The three calls
---------------
1. `profile-import` creates or updates the profile and returns its id. The email,
   the name, and the current signals go here.
2. `lists/{id}/relationships/profiles` puts that id on the list, so the result is
   visible in the Klaviyo UI. It does not change any subscription status.
3. `events` records the signals as history that nothing later overwrites.

Step 1 must run first, because only it returns the id that step 2 needs.

Why nothing sends by default
----------------------------
This writes to a live marketing system that holds real people. A wrong phone
number does not fail: it creates a second profile for someone who already has
one, and the enrichment lands on the empty copy. There is no undo. So the payload
is printed and nothing leaves the machine until you pass --send.

The identity rule
-----------------
No phone number and no email means no way to match an existing profile. In that
case this refuses to send. Sending anyway would create a profile that can never
be joined to the customer it describes.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

BASE = "https://a.klaviyo.com/api"
EVENTS_URL = f"{BASE}/events"
PROFILE_URL = f"{BASE}/profile-import"


def list_url(list_id: str) -> str:
    return f"{BASE}/lists/{list_id}/relationships/profiles"

# Klaviyo pins its API by date. An old value still works; a missing one is
# rejected. Override it when you move to a newer revision.
REVISION = os.getenv("KLAVIYO_REVISION", "2026-07-15")

METRIC_NAME = os.getenv("KLAVIYO_METRIC", "WhatsApp Signal Detected")

# Stamped on every event. Change it when the six signal definitions change, so a
# future reader can tell which rules produced which label. Segments built on the
# old labels keep meaning what they meant.
SIGNAL_SET_VERSION = "v2"

# What a person sees in Klaviyo. The machine names are for this codebase; nobody
# reading a customer profile in a marketing tool should meet "buildup_present".
SIGNAL_LABELS = {
    "absorption_blocked": "Product not absorbing",
    "hold_loss": "Curls lose definition",
    "breakage_active": "Breakage",
    "buildup_present": "Product buildup",
    "coated_feel": "Coated or waxy feel",
    "scalp_sensitivity": "Scalp sensitivity",
}


def label(signal: str) -> str:
    return SIGNAL_LABELS.get(signal, signal)


def labels_for(signals) -> list[str]:
    return sorted(label(s) for s in signals)


# E.164 allows 15 digits at most, and no real number is shorter than 8.
_MIN_DIGITS, _MAX_DIGITS = 8, 15

# One sentence is enough to judge a signal by. A longer quote copies more of a
# private support conversation into a marketing system than the check needs.
MAX_QUOTE = 300


def normalise_phone(raw: str | None) -> str | None:
    """Turn a written phone number into E.164, or return None.

    WhatsApp gives `wa_id` with no plus sign. Klaviyo wants the plus sign. This
    is the whole join key, so it is worth being strict: anything that does not
    look like a real number returns None rather than a guess.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
        return None
    return "+" + digits


def looks_like_phone(sender: str) -> bool:
    """Is this export sender a phone number rather than a saved contact name?

    WhatsApp writes the saved contact name when the agent has the customer in
    their phone, and the raw number when they do not. Only the second case gives
    you the join key.
    """
    if not re.fullmatch(r"[\d\s+\-()‪-‮]+", sender or ""):
        return False
    return normalise_phone(sender) is not None


def build_event(
    signals: list[str],
    *,
    phone: str | None,
    email: str | None,
    name: str | None,
    by_layer: dict[str, list[str]] | None = None,
    confidence: float = 0.0,
    evidence: dict[str, str] | None = None,
    source: str = "whatsapp_export",
    method: str = "judge",
    conversation_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the event payload. Makes no network call."""
    profile: dict[str, Any] = {}
    if email:
        profile["email"] = email
    if phone:
        profile["phone_number"] = phone
    if name:
        profile["first_name"] = name

    properties: dict[str, Any] = {
        "signals": labels_for(signals),
        "signal_count": len(signals),
        "signal_set": SIGNAL_SET_VERSION,
        "source": source,
        # How the labels were decided. "judge" reads the conversation; the older
        # "phrase_list" matched example phrases and fired hold_loss on the word
        # frizz. A segment built across both is comparing two different things.
        "method": method,
        "confidence": round(confidence, 2),
    }
    if by_layer:
        # Kept apart because the two layers are not equal evidence. The matching
        # layer quotes the customer. The fallback layer infers, so a segment
        # built only on inferred signals deserves a second look.
        properties["matched_signals"] = labels_for(by_layer.get("primary", []))
        properties["inferred_signals"] = labels_for(by_layer.get("fallback", []))
    if evidence:
        # The quote behind each signal, so a person reading the profile can tell
        # whether the label is right. This is the only field that lets you catch
        # a signal fired on words that do not support it.
        #
        # It goes on the event and never on the profile. A profile property can
        # be read into an email template by accident, and these are the
        # customer's own words about an inflamed scalp. An event property cannot
        # reach a template the same way.
        properties["evidence"] = {
            label(signal): quote[:MAX_QUOTE] for signal, quote in evidence.items() if quote
        }
    if conversation_id:
        # Klaviyo has no deduplication of its own. Send this on every event so a
        # repeat run is recognisable instead of silently doubling the history.
        properties["conversation_id"] = conversation_id

    attributes: dict[str, Any] = {
        "metric": {"data": {"type": "metric", "attributes": {"name": METRIC_NAME}}},
        "profile": {"data": {"type": "profile", "attributes": profile}},
        "properties": properties,
    }
    if occurred_at:
        attributes["time"] = occurred_at.astimezone(timezone.utc).isoformat()

    return {"data": {"type": "event", "attributes": attributes}}


def check_identity(phone: str | None, email: str | None) -> str | None:
    """Return the reason this must not be sent, or None when it is safe."""
    if not phone and not email:
        return (
            "No phone number and no email. Klaviyo would create a profile that "
            "cannot be matched to this customer, ever.\n"
            "       Pass --phone with their number. Open the chat in the WhatsApp "
            "Business app and tap the contact to read it.\n"
            "       An export shows the number only when the contact is unsaved "
            "AND has no profile name. A sender like '~Kety' has one, so the "
            "number never appears."
        )
    return None


def build_profile(
    signals: list[str],
    *,
    phone: str | None,
    email: str | None,
    name: str | None,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the profile upsert payload.

    Only three properties. A property holds the current state and overwrites the
    last one, so it earns its place only if you filter on it. The history lives
    on the event, which never overwrites anything.
    """
    attributes: dict[str, Any] = {}
    if email:
        attributes["email"] = email
    if phone:
        attributes["phone_number"] = phone
    if name:
        attributes["first_name"] = name

    stamp = (updated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    attributes["properties"] = {
        # A list, not a joined string. Klaviyo renders each value separately and
        # segments on "contains", so one concern can be selected without matching
        # a substring of another.
        "Hair Concerns": labels_for(signals),
        # The date, not a timestamp with microseconds. Nobody segments on the
        # second a support chat was read.
        "Hair Concerns Updated": stamp.date().isoformat(),
    }
    return {"data": {"type": "profile", "attributes": attributes}}


def build_list_add(profile_id: str) -> dict[str, Any]:
    return {"data": [{"type": "profile", "id": profile_id}]}


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Klaviyo-API-Key {key}",
        "revision": REVISION,
        # Klaviyo wants the JSON:API content type, not application/json.
        "Content-Type": "application/vnd.api+json",
        "Accept": "application/vnd.api+json",
    }


# Two names accepted, the way app/config.py takes OPENAI_API_KEY or OPEN_AI_KEY.
_KEY_NAMES = ("KLAVIYO_PRIVATE_API_KEY", "KLAVIYO_API_KEY")


def _key(api_key: str | None) -> str:
    key = api_key or next((os.getenv(n) for n in _KEY_NAMES if os.getenv(n)), None)
    if not key:
        raise RuntimeError(
            "No Klaviyo key found. Set one of " + " or ".join(_KEY_NAMES)
            + " in app/.env. Use a private key, which starts with pk_."
        )
    if not key.startswith("pk_"):
        # A public key is the six-character site id. It cannot write profiles or
        # events, and the failure it causes is a 401 that reads like a bad key.
        raise RuntimeError(
            "That Klaviyo key does not start with pk_, so it is not a private key. "
            "A public site id cannot write profiles or events."
        )
    return key


def _post(url: str, payload: dict[str, Any], api_key: str | None, timeout: float):
    import httpx

    return httpx.post(url, json=payload, timeout=timeout, headers=_headers(_key(api_key)))


def upsert_profile(payload: dict[str, Any], api_key: str | None = None, timeout: float = 15.0):
    """Create or update the profile. Answers 201 when new and 200 when it existed.

    Run this first. The list call needs the profile id, and only this call
    returns one.
    """
    return _post(PROFILE_URL, payload, api_key, timeout)


def profile_id_from(response) -> str | None:
    try:
        return response.json()["data"]["id"]
    except Exception:
        return None


def add_to_list(list_id: str, profile_id: str, api_key: str | None = None, timeout: float = 15.0):
    """Put the profile on the list. Answers 204.

    This adds a member without touching their subscription status. It is not
    consent to email or text them. A customer who messaged support on WhatsApp
    has not agreed to marketing, so use the list to see the profiles, and do not
    send a campaign to it without a separate opt-in.
    """
    return _post(list_url(list_id), build_list_add(profile_id), api_key, timeout)


def send_event(payload: dict[str, Any], api_key: str | None = None, timeout: float = 15.0):
    """POST the event. Answers 202.

    202 means Klaviyo accepted the event for processing. It does not mean the
    profile matched the one you expected. Check the profile in Klaviyo afterwards.
    """
    return _post(EVENTS_URL, payload, api_key, timeout)
