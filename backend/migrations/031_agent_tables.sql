-- Migration 031: AI Agent tables
-- Agent conversation logs and daily usage tracking for rate limiting

-- Agent conversation history
CREATE TABLE IF NOT EXISTS agent_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    response TEXT,
    model_used VARCHAR(50),
    tools_used JSONB DEFAULT '[]'::jsonb,
    tokens_used INT DEFAULT 0,
    duration_ms INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_conversations_user_id
    ON agent_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_conversations_created_at
    ON agent_conversations(created_at DESC);

-- Daily usage counters for rate limiting
CREATE TABLE IF NOT EXISTS agent_usage_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    query_count INT NOT NULL DEFAULT 0,
    UNIQUE(user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_agent_usage_daily_user_date
    ON agent_usage_daily(user_id, date);

-- Grants
GRANT ALL ON agent_conversations TO neondb_owner;
GRANT ALL ON agent_usage_daily TO neondb_owner;
