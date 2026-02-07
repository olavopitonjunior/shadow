-- Migration 027: Proactive Suggestions System
-- Creates tables for storing and managing proactive suggestions

-- Main suggestions table
CREATE TABLE IF NOT EXISTS shadow_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,

    -- Source tracking
    source_type TEXT NOT NULL CHECK (source_type IN ('entity', 'contact', 'summary', 'pattern')),
    source_id INTEGER,
    source_chat_id TEXT,
    source_message_id TEXT,

    -- Suggestion details
    suggestion_type TEXT NOT NULL CHECK (suggestion_type IN (
        'create_task', 'create_appointment', 'create_contact',
        'update_contact', 'conversation_summary'
    )),
    title TEXT NOT NULL,
    body TEXT,
    suggestion_data TEXT,  -- JSON with pre-filled tool params

    -- Scoring
    confidence REAL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    priority INTEGER DEFAULT 0 CHECK (priority >= 0 AND priority <= 3),
    -- 0=low, 1=normal, 2=high, 3=urgent

    -- State
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'sent', 'accepted', 'rejected', 'expired'
    )),
    batch_id TEXT,

    -- Timing
    send_after TEXT,      -- ISO timestamp - don't send before this
    expires_at TEXT,      -- ISO timestamp - auto-reject after this
    sent_at TEXT,
    resolved_at TEXT,

    -- User response tracking
    response_message_id TEXT,
    response_text TEXT,

    -- Timestamps
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_suggestions_owner_status ON shadow_suggestions(owner_id, status);
CREATE INDEX IF NOT EXISTS idx_suggestions_pending ON shadow_suggestions(status, send_after, priority DESC);
CREATE INDEX IF NOT EXISTS idx_suggestions_source ON shadow_suggestions(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_created ON shadow_suggestions(created_at DESC);

-- Add new columns to shadow_user_settings for suggestion preferences
-- Note: SQLite doesn't support IF NOT EXISTS for ALTER TABLE, so we handle this in Python migration

-- Suggestion rate limiting table (tracks daily counts per owner)
CREATE TABLE IF NOT EXISTS shadow_suggestion_daily_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    date TEXT NOT NULL,  -- YYYY-MM-DD format
    sent_count INTEGER DEFAULT 0,
    accepted_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(owner_id, date)
);

CREATE INDEX IF NOT EXISTS idx_suggestion_counts_owner_date ON shadow_suggestion_daily_counts(owner_id, date);
