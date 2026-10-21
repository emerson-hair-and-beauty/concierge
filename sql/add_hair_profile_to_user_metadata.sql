-- Adds the hair-profile columns collected during onboarding to user_metadata.
-- Until now this table only held identity fields (first_name, location,
-- gender, email, hair_length); the decision-state pipeline needs texture,
-- density, porosity, humidity response, and hair goals to build a
-- ProfileState server-side. Idempotent; safe to run multiple times.

BEGIN;

ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS texture             TEXT;
ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS density             TEXT;
ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS moisture_behaviour  TEXT;
ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS humidity_response   TEXT;
ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS hair_goals          TEXT[];
ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS scalp               TEXT;
ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS damage              TEXT;

COMMIT;
