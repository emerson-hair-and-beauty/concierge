"""
Push Notification Service: Manages Web Push subscriptions and sending notifications.
"""

import os
from typing import Optional, List, Dict
from pywebpush import webpush, WebPushException
from app.services.supabase_service import get_supabase


async def store_subscription(
    user_id: str,
    endpoint: str,
    p256dh: str,
    auth: str
) -> bool:
    """
    Store or update a user's push subscription.

    Args:
        user_id: User identifier
        endpoint: Push service endpoint URL
        p256dh: Encryption key
        auth: Authentication secret

    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase()

    try:
        # Upsert into push_subscriptions table
        supabase.table("push_subscriptions").upsert({
            "user_id": user_id,
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth
        }).execute()

        print(f"[PUSH] Stored subscription for user {user_id}")
        return True

    except Exception as e:
        print(f"[PUSH] Error storing subscription: {str(e)}")
        return False


async def get_subscriptions(user_id: str) -> List[Dict]:
    """
    Fetch all push subscriptions for a user.

    Args:
        user_id: User identifier

    Returns:
        List of subscription dicts with endpoint, p256dh, auth
    """
    supabase = get_supabase()

    try:
        response = supabase.table("push_subscriptions") \
            .select("endpoint, p256dh, auth") \
            .eq("user_id", user_id) \
            .execute()

        return response.data or []

    except Exception as e:
        print(f"[PUSH] Error fetching subscriptions: {str(e)}")
        return []


async def send_push_notification(
    user_id: str,
    title: str,
    body: str,
    data: Optional[Dict] = None
) -> bool:
    """
    Send a push notification to all of a user's subscriptions.

    Args:
        user_id: User identifier
        title: Notification title
        body: Notification body/message
        data: Optional data dict (e.g. {"url": "/routine/summary"})

    Returns:
        True if all sends successful, False otherwise
    """
    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY")
    vapid_public_key = os.getenv("NEXT_PUBLIC_VAPID_PUBLIC_KEY")
    vapid_claims = {
        "sub": "mailto:admin@concierge.example.com",  # Change to your email
    }

    if not vapid_private_key or not vapid_public_key:
        print("[PUSH] VAPID keys not configured")
        return False

    subscriptions = await get_subscriptions(user_id)

    if not subscriptions:
        print(f"[PUSH] No subscriptions found for user {user_id}")
        return False

    payload = {
        "title": title,
        "body": body,
        "icon": "/icons/icon-192x192.png",
        "badge": "/icons/icon-192x192.png",
    }

    if data:
        payload.update(data)

    all_successful = True

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {
                        "p256dh": sub["p256dh"],
                        "auth": sub["auth"]
                    }
                },
                data=str(payload),  # pywebpush requires string payload
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,
                timeout=10
            )
            print(f"[PUSH] Sent to {sub['endpoint']}")

        except WebPushException as e:
            print(f"[PUSH] WebPush error: {str(e)}")
            all_successful = False
        except Exception as e:
            print(f"[PUSH] Error sending notification: {str(e)}")
            all_successful = False

    return all_successful


def remove_subscription(user_id: str, endpoint: str) -> bool:
    """
    Remove a specific push subscription (useful if endpoint is invalid).

    Args:
        user_id: User identifier
        endpoint: Endpoint to remove

    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase()

    try:
        supabase.table("push_subscriptions") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("endpoint", endpoint) \
            .execute()

        print(f"[PUSH] Removed subscription for {endpoint}")
        return True

    except Exception as e:
        print(f"[PUSH] Error removing subscription: {str(e)}")
        return False
