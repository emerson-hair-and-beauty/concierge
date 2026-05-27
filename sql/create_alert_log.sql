-- Unified alerts table. Replaces pending_alerts.
-- Serves both:
--   * dedup ledger for in-chat alerts (sent_at + cooldown comparisons)
--   * banner inbox for cron-fired scenario alerts (is_read flag)
CREATE TABLE IF NOT EXISTS alert_log (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id      TEXT        NOT NULL,
    source_type  TEXT        NOT NULL,
    source_id    TEXT        NOT NULL,
    alert_type   TEXT        NOT NULL,
    scenario     TEXT,
    prompt       TEXT,
    is_read      BOOLEAN     NOT NULL DEFAULT FALSE,
    sent_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_log_user_id            ON alert_log (user_id);
CREATE INDEX IF NOT EXISTS idx_alert_log_source_type        ON alert_log (source_type);
CREATE INDEX IF NOT EXISTS idx_alert_log_user_type_sent_at  ON alert_log (user_id, alert_type, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_user_unread        ON alert_log (user_id, is_read);
