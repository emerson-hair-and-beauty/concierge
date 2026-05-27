-- One-time migration: upgrade alert_log to the unified schema and import
-- existing pending_alerts rows. Safe to run multiple times.
--
-- Run AFTER create_alert_log.sql has been applied (or together; this script
-- is defensive about both states).

BEGIN;

-- 1. Drop the legacy UNIQUE (user_id, alert_type) constraint if it exists.
--    The cooldown model allows multiple rows for the same (user, alert_type)
--    over time, so this constraint must go.
ALTER TABLE alert_log DROP CONSTRAINT IF EXISTS alert_log_user_id_alert_type_key;

-- 2. Add the new columns (idempotent).
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS scenario TEXT;
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS prompt   TEXT;
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS is_read  BOOLEAN NOT NULL DEFAULT FALSE;

-- 3. Add the new indexes (idempotent).
CREATE INDEX IF NOT EXISTS idx_alert_log_user_type_sent_at ON alert_log (user_id, alert_type, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_user_unread       ON alert_log (user_id, is_read);

-- 4. Migrate pending_alerts data into alert_log.
--    Legacy rows are tagged source_type='legacy_scenario'; alert_type mirrors
--    the scenario label so cooldown lookups for the same scenario find them.
INSERT INTO alert_log (
    id, user_id, source_type, source_id, alert_type, scenario, prompt, is_read, sent_at
)
SELECT
    pa.id,
    pa.user_id,
    'legacy_scenario'                                AS source_type,
    pa.scenario                                      AS source_id,
    pa.scenario                                      AS alert_type,
    pa.scenario                                      AS scenario,
    pa.prompt                                        AS prompt,
    COALESCE(pa.is_read, FALSE)                      AS is_read,
    COALESCE(pa.created_at, NOW())                   AS sent_at
FROM pending_alerts pa
WHERE NOT EXISTS (
    SELECT 1 FROM alert_log al WHERE al.id = pa.id
);

COMMIT;

-- After verifying the migrated rows in alert_log, run separately:
--   DROP TABLE pending_alerts;
