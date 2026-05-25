-- Create the routine_recommendations table
CREATE TABLE IF NOT EXISTS routine_recommendations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    reasoning TEXT,
    routine_step_ref TEXT,
    recommendation_type TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now(),
    decided_at TIMESTAMPTZ
);

-- Create index on user_id + status for efficient fetching
CREATE INDEX IF NOT EXISTS idx_recommendations_user_status
    ON routine_recommendations(user_id, status);

-- Create the push_subscriptions table for Web Push API
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create index on user_id for push lookups
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id
    ON push_subscriptions(user_id);
