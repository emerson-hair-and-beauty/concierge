-- Phase 4: Retire pending_alerts.
--
-- Prerequisite: sql/migrate_alert_log_v2.sql has been run and the data has been
-- verified inside alert_log. The application no longer reads or writes
-- pending_alerts after this commit.
--
-- Also drops the legacy daily-dedup column on user_metadata; cooldown_days on
-- the rule definitions has taken over.

BEGIN;

DROP TABLE IF EXISTS pending_alerts;

ALTER TABLE user_metadata DROP COLUMN IF EXISTS last_weather_alert_sent;

COMMIT;
