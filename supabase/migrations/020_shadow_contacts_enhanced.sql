-- Migration: Enhanced Contact Management
-- Phase 5: Schema enhancements for contact resolution, summarization, and memory

-- =====================================================
-- SHADOW_CONTACTS - Additional fields
-- =====================================================
ALTER TABLE shadow_contacts ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE shadow_contacts ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE shadow_contacts ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]';
ALTER TABLE shadow_contacts ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'message';
  -- source: 'message' (auto from chat), 'manual' (user created), 'import'

COMMENT ON COLUMN shadow_contacts.email IS 'Contact email address';
COMMENT ON COLUMN shadow_contacts.notes IS 'Free-form notes about the contact';
COMMENT ON COLUMN shadow_contacts.tags IS 'Array of tags for categorization';
COMMENT ON COLUMN shadow_contacts.source IS 'How contact was created: message, manual, import';

-- =====================================================
-- SHADOW_CONTACT_CONTEXT - Additional fields
-- =====================================================
ALTER TABLE shadow_contact_context ADD COLUMN IF NOT EXISTS relationship_type TEXT;
ALTER TABLE shadow_contact_context ADD COLUMN IF NOT EXISTS last_summary_at TIMESTAMPTZ;
ALTER TABLE shadow_contact_context ADD COLUMN IF NOT EXISTS summary_message_count INTEGER DEFAULT 0;

COMMENT ON COLUMN shadow_contact_context.relationship_type IS 'Type: client, colleague, supplier, friend, family, other';
COMMENT ON COLUMN shadow_contact_context.last_summary_at IS 'When summary was last generated';
COMMENT ON COLUMN shadow_contact_context.summary_message_count IS 'Message count at last summary generation';

-- =====================================================
-- SHADOW_CONTACT_ALIASES - Name resolution table
-- =====================================================
CREATE TABLE IF NOT EXISTS shadow_contact_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    alias TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, alias)
);

COMMENT ON TABLE shadow_contact_aliases IS 'Maps aliases/nicknames to contact phones for name resolution';
COMMENT ON COLUMN shadow_contact_aliases.owner_id IS 'Owner user phone';
COMMENT ON COLUMN shadow_contact_aliases.contact_phone IS 'Contact phone number (E164)';
COMMENT ON COLUMN shadow_contact_aliases.alias IS 'Alternative name/nickname for the contact';

-- Indexes for alias lookups
CREATE INDEX IF NOT EXISTS idx_contact_aliases_owner ON shadow_contact_aliases(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_aliases_alias ON shadow_contact_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_contact_aliases_phone ON shadow_contact_aliases(contact_phone);

-- =====================================================
-- SHADOW_CONTACT_MEMORIES - Semantic memory (LanceDB backup)
-- =====================================================
-- Note: Primary semantic search uses LanceDB locally
-- This table provides backup/sync for cloud deployments
CREATE TABLE IF NOT EXISTS shadow_contact_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    contact_phone TEXT,
    text TEXT NOT NULL,
    category TEXT DEFAULT 'interaction'
        CHECK (category IN ('preference', 'fact', 'decision', 'entity', 'interaction')),
    importance REAL DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE shadow_contact_memories IS 'Semantic memories about contacts (backup for LanceDB)';
COMMENT ON COLUMN shadow_contact_memories.category IS 'Memory type: preference, fact, decision, entity, interaction';
COMMENT ON COLUMN shadow_contact_memories.importance IS 'Importance score 0-1';

CREATE INDEX IF NOT EXISTS idx_contact_memories_owner ON shadow_contact_memories(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_memories_phone ON shadow_contact_memories(contact_phone);
CREATE INDEX IF NOT EXISTS idx_contact_memories_category ON shadow_contact_memories(category);

-- =====================================================
-- Full-text search index for contact names
-- =====================================================
-- Enable Portuguese text search on contact_name
CREATE INDEX IF NOT EXISTS idx_contact_context_name_search
ON shadow_contact_context USING gin(to_tsvector('portuguese', COALESCE(contact_name, '')));
