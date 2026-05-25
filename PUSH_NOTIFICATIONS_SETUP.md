# Push Notifications Setup Guide

## Overview

This guide explains how to set up Web Push Notifications for the Concierge app using VAPID (Voluntary Application Server Identification) keys.

## Prerequisites

- Node.js installed locally
- Both frontend (concierge-web-demo) and backend (concierge-1) projects set up
- Service worker enabled (via next-pwa on the frontend)

## Step 1: Generate VAPID Keys

Generate a unique pair of VAPID keys using the `web-push` CLI:

```bash
npm install -g web-push

web-push generate-vapid-keys
```

This will output:
```
Public Key: <YOUR_PUBLIC_KEY>
Private Key: <YOUR_PRIVATE_KEY>
```

## Step 2: Configure Environment Variables

### Backend (concierge-1)

In `concierge-1/.env`, add:

```env
VAPID_PRIVATE_KEY=<YOUR_PRIVATE_KEY>
```

### Frontend (concierge-web-demo)

In `concierge-web-demo/.env.local`, add:

```env
NEXT_PUBLIC_VAPID_PUBLIC_KEY=<YOUR_PUBLIC_KEY>
```

## Step 3: Create Supabase Tables

Run the migration SQL from `concierge-1/sql/01_recommendations_tables.sql`:

```sql
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id
    ON push_subscriptions(user_id);
```

Execute this in your Supabase console or via the Supabase CLI.

## Step 4: Install Backend Dependencies

In `concierge-1/`:

```bash
pip install pywebpush
```

Or add `pywebpush` to `requirements.txt` and run:

```bash
pip install -r requirements.txt
```

## Step 5: Test the Flow

1. **Frontend**: User visits the app and sees the install prompt
2. **Frontend**: User accepts a recommendation → system may prompt for push notification permission
3. **Frontend**: On permission grant, service worker subscribes via `/api/push/subscribe`
4. **Backend**: Subscription is stored in `push_subscriptions` table
5. **Backend**: When recommendations are generated, backend sends push via `send_push_notification()`

### Manual Testing

To manually send a test push notification:

```python
from app.services.recommendations.push_service import send_push_notification
import asyncio

async def test():
    result = await send_push_notification(
        user_id="test_user_id",
        title="Test Notification",
        body="This is a test push notification",
        data={"url": "/routine/summary"}
    )
    print(f"Push sent: {result}")

asyncio.run(test())
```

## Troubleshooting

### VAPID Keys Not Configured
- Error: "VAPID keys not configured"
- Solution: Ensure `VAPID_PRIVATE_KEY` env var is set on the backend and `NEXT_PUBLIC_VAPID_PUBLIC_KEY` is set on the frontend

### Service Worker Not Registering
- Error: Service worker fails to register
- Solution: Check browser console for CORS or other errors. Ensure `next-pwa` is properly configured in `next.config.mjs`

### Push Permission Denied
- Error: User denies notification permission
- Solution: Prompt for permission at an appropriate moment (e.g., after first recommendation acceptance)

### Push Subscription Fails
- Error: 410 Gone or 401 Unauthorized
- Solution: Subscription endpoint may be invalid or expired. Delete stale subscriptions from `push_subscriptions` table

## Push Notification Flow Diagram

```
User -> App -> Service Worker -> Push Manager -> Browser Notification
           ↓
       `/api/push/subscribe` (stores in DB)
           ↓
Backend (generates recommendation) -> `send_push_notification()` 
           ↓
       pywebpush -> Push Service
           ↓
Service Worker (sw.js) -> `push` event -> `showNotification()`
           ↓
User clicks notification -> `notificationclick` event -> Opens app
```

## References

- [Web Push Protocol](https://datatracker.ietf.org/doc/html/draft-thomson-webpush-protocol)
- [Web Notifications API](https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API)
- [Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API)
- [pywebpush](https://github.com/web-push-libs/pywebpush)
