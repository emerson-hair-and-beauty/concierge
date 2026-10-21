-- Adds first_name to user_metadata. The orchestrator saves first_name with the
-- hair profile; without this column Supabase rejects the whole upsert, so the
-- hair profile never saves either. Idempotent; safe to run multiple times.

BEGIN;

ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS first_name TEXT;

COMMIT;
