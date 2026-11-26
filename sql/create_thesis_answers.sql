-- One row for each answer to a thesis question (app/services/thesis/thesis_answers.py).
-- path_changed = false means the answer did not move the decision engine.
CREATE TABLE IF NOT EXISTS thesis_answers (
    id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id       TEXT        NOT NULL,
    session_id    TEXT        NOT NULL,
    thesis        TEXT        NOT NULL,
    rival         TEXT,
    question      TEXT        NOT NULL,
    options       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    answer        TEXT        NOT NULL,
    path_after    TEXT,
    path_changed  BOOLEAN     NOT NULL,
    signals_after JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_thesis_answers_session_id ON thesis_answers (session_id);

-- The app uses the publishable key. It can add rows but cannot read them,
-- so the guests' answers stay private. Read them in the Supabase dashboard.
ALTER TABLE thesis_answers ENABLE ROW LEVEL SECURITY;
CREATE POLICY thesis_answers_insert_only ON thesis_answers
    FOR INSERT TO anon, authenticated WITH CHECK (true);

-- Hide the table from the public API schema. Inserts with returning=minimal need no SELECT.
REVOKE SELECT, UPDATE, DELETE ON thesis_answers FROM anon, authenticated;
