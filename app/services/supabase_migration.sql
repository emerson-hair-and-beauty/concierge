-- ============================================
-- Supabase Migration: Persistent Brain System
-- Two-Speed Memory Architecture
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- Short-Term Memory: Live Chat Transcripts
-- ============================================

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,      -- Firebase user ID for hierarchical structure
    session_id TEXT NOT NULL,
    role TEXT CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Composite index for user + session queries (most common pattern)
CREATE INDEX idx_chat_messages_user_session ON chat_messages(user_id, session_id, created_at DESC);

-- Index for session-only queries (backward compatibility)
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, created_at DESC);

-- Index for user-only queries (to get all sessions for a user)
CREATE INDEX idx_chat_messages_user ON chat_messages(user_id, created_at DESC);

COMMENT ON TABLE chat_messages IS 'Short-Term Memory: Stores live chat transcripts for session continuity';
COMMENT ON COLUMN chat_messages.user_id IS 'Firebase user ID (string format) - enables user → session → messages hierarchy';
COMMENT ON COLUMN chat_messages.session_id IS 'Client-generated session identifier';
COMMENT ON COLUMN chat_messages.role IS 'Message sender: user or assistant';

-- ============================================
-- Long-Term Memory: The "Librarian" Filing Cabinet
-- ============================================

CREATE TABLE hair_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,  -- Firebase user ID (string)
    primary_label TEXT,     -- Event category (e.g., MOISTURE, SCALP, DEFINITION, BREAKAGE)
    summary TEXT,           -- Dense diagnostic summary
    vital_score INTEGER,    -- User-provided severity score (1-10)
    metadata JSONB,         -- Flexible storage: wash_day, keywords, session_id, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast user + category queries (most recent first)
CREATE INDEX idx_hair_events_user_category ON hair_events(user_id, primary_label, created_at DESC);

-- Index for user-only queries
CREATE INDEX idx_hair_events_user ON hair_events(user_id, created_at DESC);

COMMENT ON TABLE hair_events IS 'Long-Term Memory: Event-driven diagnostic history for personalized recommendations';
COMMENT ON COLUMN hair_events.user_id IS 'Firebase user ID (string format)';
COMMENT ON COLUMN hair_events.primary_label IS 'LLM-generated category tag for event classification';
COMMENT ON COLUMN hair_events.metadata IS 'JSONB storage for wash_day, keywords, session_id, and other contextual data';

-- ============================================
-- Routine Data: Persistent Hair Care Plans
-- ============================================

CREATE TABLE user_routines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,  -- Firebase user ID (string)
    routine_json JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for active routine queries (most recent first)
CREATE INDEX idx_user_routines_active ON user_routines(user_id, is_active, created_at DESC);

-- Index for user-only queries
CREATE INDEX idx_user_routines_user ON user_routines(user_id, created_at DESC);

COMMENT ON TABLE user_routines IS 'Persistent storage for AI-generated hair care routines';
COMMENT ON COLUMN user_routines.user_id IS 'Firebase user ID (string format)';
COMMENT ON COLUMN user_routines.routine_json IS 'Complete routine structure with steps, ingredients, and product recommendations';
COMMENT ON COLUMN user_routines.is_active IS 'Flag to mark the currently active routine for the user';

-- ============================================
-- Row Level Security (RLS) Policies
-- ============================================
-- Note: These are disabled for now since we're using Firebase Auth
-- Uncomment and modify when migrating to Supabase Auth

-- ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE hair_events ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE user_routines ENABLE ROW LEVEL SECURITY;

-- Example policy (when using Supabase Auth):
-- CREATE POLICY "Users can view their own events" ON hair_events
--     FOR SELECT USING (auth.uid()::text = user_id);
