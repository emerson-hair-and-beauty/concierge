CREATE TABLE IF NOT EXISTS signal_events (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id          TEXT        NOT NULL,
    session_id       TEXT        NOT NULL,
    signal_type      TEXT        NOT NULL,
    first_detected_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    UNIQUE (session_id, signal_type)
);

CREATE INDEX IF NOT EXISTS idx_signal_events_user_id    ON signal_events (user_id);
CREATE INDEX IF NOT EXISTS idx_signal_events_session_id ON signal_events (session_id);
