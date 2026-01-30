-- Shadow Entity Extraction Tables
-- Migration: 017_shadow_entities.sql
-- Purpose: Store extracted entities (tasks, meetings, contacts, reminders) from conversations

-- Extracted entities from messages
CREATE TABLE IF NOT EXISTS shadow_extracted_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    source_chat_id TEXT NOT NULL,
    source_message_id TEXT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('task', 'meeting', 'contact', 'reminder')),
    entity_data JSONB NOT NULL DEFAULT '{}',
    confidence REAL DEFAULT 0.8 CHECK (confidence >= 0 AND confidence <= 1),
    extracted_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_entities_owner ON shadow_extracted_entities(owner_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON shadow_extracted_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_chat ON shadow_extracted_entities(source_chat_id);
CREATE INDEX IF NOT EXISTS idx_entities_extracted ON shadow_extracted_entities(extracted_at DESC);
CREATE INDEX IF NOT EXISTS idx_entities_processed ON shadow_extracted_entities(processed) WHERE NOT processed;

-- Contact context (summary of conversations per contact)
CREATE TABLE IF NOT EXISTS shadow_contact_context (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    contact_name TEXT,
    last_interaction TIMESTAMPTZ,
    interaction_count INTEGER DEFAULT 0,
    message_count INTEGER DEFAULT 0,
    summary TEXT,
    topics JSONB DEFAULT '[]',
    sentiment TEXT CHECK (sentiment IN ('positive', 'neutral', 'negative', NULL)),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, contact_phone)
);

-- Indexes for contact context
CREATE INDEX IF NOT EXISTS idx_contact_context_owner ON shadow_contact_context(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_context_phone ON shadow_contact_context(contact_phone);
CREATE INDEX IF NOT EXISTS idx_contact_context_name ON shadow_contact_context(contact_name);
CREATE INDEX IF NOT EXISTS idx_contact_context_last ON shadow_contact_context(last_interaction DESC);

-- Task-contact relationships (link tasks to mentioned contacts)
CREATE TABLE IF NOT EXISTS shadow_task_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    contact_phone TEXT,
    contact_name TEXT,
    relation_type TEXT DEFAULT 'mentioned' CHECK (relation_type IN ('mentioned', 'assigned', 'requester', 'participant')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(task_id, COALESCE(contact_phone, ''), COALESCE(contact_name, ''))
);

-- Indexes for task contacts
CREATE INDEX IF NOT EXISTS idx_task_contacts_task ON shadow_task_contacts(task_id);
CREATE INDEX IF NOT EXISTS idx_task_contacts_phone ON shadow_task_contacts(contact_phone);
CREATE INDEX IF NOT EXISTS idx_task_contacts_name ON shadow_task_contacts(contact_name);

-- Function to update contact context timestamp
CREATE OR REPLACE FUNCTION update_contact_context_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-updating timestamp
DROP TRIGGER IF EXISTS trigger_contact_context_updated ON shadow_contact_context;
CREATE TRIGGER trigger_contact_context_updated
    BEFORE UPDATE ON shadow_contact_context
    FOR EACH ROW
    EXECUTE FUNCTION update_contact_context_timestamp();

-- Enable RLS on all new tables
ALTER TABLE shadow_extracted_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_contact_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_task_contacts ENABLE ROW LEVEL SECURITY;

-- RLS Policies for shadow_extracted_entities
CREATE POLICY "Users see own entities" ON shadow_extracted_entities
    FOR ALL USING (owner_id = current_setting('app.current_owner', true));

-- RLS Policies for shadow_contact_context
CREATE POLICY "Users see own contact context" ON shadow_contact_context
    FOR ALL USING (owner_id = current_setting('app.current_owner', true));

-- RLS Policies for shadow_task_contacts (via task ownership - simplified)
CREATE POLICY "Users manage task contacts" ON shadow_task_contacts
    FOR ALL USING (true);

-- Helper function to set current owner for RLS
CREATE OR REPLACE FUNCTION set_shadow_owner(owner_phone TEXT)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.current_owner', owner_phone, true);
END;
$$ LANGUAGE plpgsql;
