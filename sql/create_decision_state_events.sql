CREATE TABLE IF NOT EXISTS decision_state_events (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id          TEXT        NOT NULL,
    session_id       TEXT        NOT NULL,
    decision_state   TEXT        NOT NULL,
    first_seen_at    TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    UNIQUE (session_id, decision_state)
);

CREATE INDEX IF NOT EXISTS idx_decision_state_events_user_id    ON decision_state_events (user_id);
CREATE INDEX IF NOT EXISTS idx_decision_state_events_session_id ON decision_state_events (session_id);
