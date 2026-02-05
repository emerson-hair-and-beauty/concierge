-- Migration: Add user_id to chat_messages table
-- Run this in Supabase SQL Editor to update existing table

-- Step 1: Add user_id column (nullable first to avoid breaking existing data)
ALTER TABLE chat_messages 
ADD COLUMN IF NOT EXISTS user_id TEXT;

-- Step 2: Update existing rows with a placeholder user_id (if any exist)
UPDATE chat_messages 
SET user_id = 'legacy-user' 
WHERE user_id IS NULL;

-- Step 3: Make user_id NOT NULL now that all rows have a value
ALTER TABLE chat_messages 
ALTER COLUMN user_id SET NOT NULL;

-- Step 4: Add new composite indexes
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_session 
ON chat_messages(user_id, session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_messages_user 
ON chat_messages(user_id, created_at DESC);

-- Step 5: Add comment
COMMENT ON COLUMN chat_messages.user_id IS 'Firebase user ID (string format) - enables user → session → messages hierarchy';

-- Verify the changes
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'chat_messages' 
ORDER BY ordinal_position;
