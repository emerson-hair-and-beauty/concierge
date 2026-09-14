"""Customer enrichment from WhatsApp conversations.

This package reads WhatsApp conversations, finds the hair signals the concierge
already detects, pulls out the email and the name, and prepares the result for
Klaviyo.

It imports from `app` and `app` never imports from here. Keep that direction.
The six signal definitions live in `app/services/session_signal/signal_detector.py`
and must stay in one place. A second copy would drift away from the first, and
nothing would warn you.

Status: only the parts that need no external approval are built. The WhatsApp
number is not on the Cloud API yet, so nothing reads a live webhook. The current
input is a chat export produced by hand from the WhatsApp Business app.
"""
