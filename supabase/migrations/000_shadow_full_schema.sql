-- ============================================================================
-- SHADOW MVP - FULL SCHEMA CONSOLIDATED
-- ============================================================================
-- Execute this file in Supabase SQL Editor to create all tables
-- Order: Dependencies first, then dependent tables
-- ============================================================================

-- ============================================================================
-- 001: Access Codes (Admin Authentication)
-- ============================================================================
CREATE TABLE IF NOT EXISTS access_codes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code VARCHAR(20) UNIQUE NOT NULL,
  role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'user')),
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_access_codes_code ON access_codes(code);

INSERT INTO access_codes (code, role)
SELECT 'ADMIN001', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM access_codes WHERE code = 'ADMIN001');

-- ============================================================================
-- 009: Organizations (REQUIRED for sessions/cron_jobs)
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  plan TEXT DEFAULT 'starter',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shadow_organizations_slug ON shadow_organizations(slug);

-- ============================================================================
-- 010: Core Shadow MVP Schema
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID REFERENCES shadow_organizations(id),
  phone_number TEXT UNIQUE NOT NULL,
  whatsapp_type TEXT DEFAULT 'personal',
  role_in_org TEXT DEFAULT 'owner',
  name TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shadow_contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  phone_number TEXT,
  name TEXT NOT NULL,
  company TEXT,
  email TEXT,
  notes TEXT,
  tags JSONB DEFAULT '[]',
  source TEXT DEFAULT 'message',
  last_interaction_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  deleted_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, phone_number)
);

CREATE TABLE IF NOT EXISTS shadow_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  chat_id TEXT,
  chat_type TEXT DEFAULT 'direct',
  started_at TIMESTAMPTZ DEFAULT NOW(),
  last_message_at TIMESTAMPTZ,
  summary TEXT,
  UNIQUE(user_id, chat_id)
);

CREATE TABLE IF NOT EXISTS shadow_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES shadow_conversations(id),
  direction TEXT CHECK (direction IN ('inbound', 'outbound')) NOT NULL,
  content TEXT NOT NULL,
  content_type TEXT CHECK (content_type IN ('text', 'audio', 'image', 'document')) DEFAULT 'text',
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shadow_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  title TEXT NOT NULL,
  description TEXT,
  due_date TIMESTAMPTZ,
  status TEXT CHECK (status IN ('pending', 'done', 'cancelled', 'completed', 'deleted')) DEFAULT 'pending',
  category_id UUID,
  priority TEXT DEFAULT 'normal',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS shadow_appointments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  title TEXT NOT NULL,
  description TEXT,
  scheduled_at TIMESTAMPTZ NOT NULL,
  duration_minutes INTEGER DEFAULT 60,
  status TEXT CHECK (status IN ('scheduled', 'completed', 'cancelled')) DEFAULT 'scheduled',
  type_id UUID,
  location TEXT,
  video_link TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shadow_interactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  user_message TEXT NOT NULL,
  shadow_response TEXT NOT NULL,
  intent TEXT,
  entities_created JSONB,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shadow_reminders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  task_id UUID REFERENCES shadow_tasks(id),
  appointment_id UUID REFERENCES shadow_appointments(id),
  remind_at TIMESTAMPTZ NOT NULL,
  message TEXT NOT NULL,
  sent BOOLEAN DEFAULT FALSE,
  attempts INTEGER DEFAULT 0,
  last_error TEXT,
  sent_at TIMESTAMPTZ,
  failed BOOLEAN DEFAULT FALSE,
  target_phone TEXT,
  recipient_source TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Core indexes
CREATE INDEX IF NOT EXISTS idx_shadow_contacts_user ON shadow_contacts(user_id);
CREATE INDEX IF NOT EXISTS idx_shadow_contacts_active ON shadow_contacts(user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_shadow_tasks_user_status ON shadow_tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_shadow_appointments_user_date ON shadow_appointments(user_id, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_shadow_messages_conversation ON shadow_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_shadow_reminders_pending ON shadow_reminders(remind_at) WHERE sent = FALSE AND failed = FALSE;
CREATE INDEX IF NOT EXISTS idx_shadow_reminders_failed ON shadow_reminders(failed) WHERE failed = TRUE;
CREATE INDEX IF NOT EXISTS idx_shadow_reminders_target_phone ON shadow_reminders(target_phone) WHERE target_phone IS NOT NULL;

-- ============================================================================
-- 012-013: Shadow Config
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_phone TEXT,
  ignore_groups BOOLEAN DEFAULT TRUE,
  store_relevant_only BOOLEAN DEFAULT TRUE,
  enable_shadow_replies BOOLEAN DEFAULT TRUE,
  evolution_api_url TEXT,
  evolution_api_key TEXT,
  evolution_instance_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO shadow_config (owner_phone)
SELECT NULL WHERE NOT EXISTS (SELECT 1 FROM shadow_config);

-- ============================================================================
-- 014: Webhook Logs
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_webhook_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT,
  user_phone TEXT,
  contact_phone TEXT,
  direction TEXT,
  content TEXT,
  content_type TEXT,
  is_group BOOLEAN,
  received_at TIMESTAMPTZ DEFAULT NOW(),
  payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_shadow_webhook_logs_received_at ON shadow_webhook_logs(received_at DESC);

-- ============================================================================
-- 015: Cron Jobs
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_cron_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES shadow_users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES shadow_organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('at', 'every', 'cron')),
    schedule_at_ms BIGINT,
    schedule_every_ms BIGINT,
    schedule_anchor_ms BIGINT,
    schedule_expr TEXT,
    schedule_tz TEXT DEFAULT 'America/Sao_Paulo',
    action TEXT NOT NULL,
    params JSONB DEFAULT '{}',
    enabled BOOLEAN DEFAULT true,
    delete_after_run BOOLEAN DEFAULT false,
    state_next_run_at_ms BIGINT,
    state_running_at_ms BIGINT,
    state_last_run_at_ms BIGINT,
    state_last_status TEXT CHECK (state_last_status IN ('ok', 'error', 'skipped')),
    state_last_error TEXT,
    state_last_duration_ms BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shadow_cron_jobs_user ON shadow_cron_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_shadow_cron_jobs_enabled ON shadow_cron_jobs(enabled) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_shadow_cron_jobs_next_run ON shadow_cron_jobs(state_next_run_at_ms) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_shadow_cron_jobs_action ON shadow_cron_jobs(action);

-- ============================================================================
-- 016: Sessions
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES shadow_users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES shadow_organizations(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL,
    participant_phone TEXT,
    kind TEXT NOT NULL DEFAULT 'direct' CHECK (kind IN ('direct', 'group')),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'idle', 'closed')),
    context_window JSONB DEFAULT '[]',
    context_summary TEXT,
    defaults JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    label TEXT,
    display_name TEXT,
    message_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, chat_id)
);

CREATE INDEX IF NOT EXISTS idx_shadow_sessions_user ON shadow_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_chat ON shadow_sessions(chat_id);
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_participant ON shadow_sessions(participant_phone);
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_status ON shadow_sessions(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_activity ON shadow_sessions(last_activity_at DESC);

-- ============================================================================
-- 017: Entity Extraction
-- ============================================================================
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

CREATE INDEX IF NOT EXISTS idx_entities_owner ON shadow_extracted_entities(owner_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON shadow_extracted_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_chat ON shadow_extracted_entities(source_chat_id);
CREATE INDEX IF NOT EXISTS idx_entities_extracted ON shadow_extracted_entities(extracted_at DESC);
CREATE INDEX IF NOT EXISTS idx_entities_processed ON shadow_extracted_entities(processed) WHERE NOT processed;

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
    relationship_type TEXT,
    last_summary_at TIMESTAMPTZ,
    summary_message_count INTEGER DEFAULT 0,
    deleted_at TIMESTAMPTZ,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, contact_phone)
);

CREATE INDEX IF NOT EXISTS idx_contact_context_owner ON shadow_contact_context(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_context_phone ON shadow_contact_context(contact_phone);
CREATE INDEX IF NOT EXISTS idx_contact_context_name ON shadow_contact_context(contact_name);
CREATE INDEX IF NOT EXISTS idx_contact_context_last ON shadow_contact_context(last_interaction DESC);
CREATE INDEX IF NOT EXISTS idx_contact_context_active ON shadow_contact_context(owner_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS shadow_task_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    contact_phone TEXT,
    contact_name TEXT,
    relation_type TEXT DEFAULT 'mentioned' CHECK (relation_type IN ('mentioned', 'assigned', 'requester', 'participant')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique index with COALESCE (workaround for nullable columns)
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_contacts_unique
ON shadow_task_contacts(task_id, COALESCE(contact_phone, ''), COALESCE(contact_name, ''));

CREATE INDEX IF NOT EXISTS idx_task_contacts_task ON shadow_task_contacts(task_id);
CREATE INDEX IF NOT EXISTS idx_task_contacts_phone ON shadow_task_contacts(contact_phone);
CREATE INDEX IF NOT EXISTS idx_task_contacts_name ON shadow_task_contacts(contact_name);

-- ============================================================================
-- 020: Contact Aliases & Memories
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_contact_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    alias TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, alias)
);

CREATE INDEX IF NOT EXISTS idx_contact_aliases_owner ON shadow_contact_aliases(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_aliases_alias ON shadow_contact_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_contact_aliases_phone ON shadow_contact_aliases(contact_phone);

CREATE TABLE IF NOT EXISTS shadow_contact_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    contact_phone TEXT,
    text TEXT NOT NULL,
    category TEXT DEFAULT 'interaction' CHECK (category IN ('preference', 'fact', 'decision', 'entity', 'interaction')),
    importance REAL DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contact_memories_owner ON shadow_contact_memories(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_memories_phone ON shadow_contact_memories(contact_phone);
CREATE INDEX IF NOT EXISTS idx_contact_memories_category ON shadow_contact_memories(category);

-- ============================================================================
-- 021: Contact Management (Merges & Duplicates)
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_contact_merges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    target_phone TEXT NOT NULL,
    source_phone TEXT NOT NULL,
    source_name TEXT,
    merged_at TIMESTAMPTZ DEFAULT NOW(),
    merged_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_contact_merges_owner ON shadow_contact_merges(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_merges_target ON shadow_contact_merges(target_phone);

CREATE TABLE IF NOT EXISTS shadow_contact_duplicates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    phone_a TEXT NOT NULL,
    phone_b TEXT NOT NULL,
    similarity_score REAL NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'rejected', 'merged')),
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    UNIQUE(owner_id, phone_a, phone_b)
);

CREATE INDEX IF NOT EXISTS idx_contact_duplicates_owner ON shadow_contact_duplicates(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_duplicates_pending ON shadow_contact_duplicates(owner_id, status) WHERE status = 'pending';

-- ============================================================================
-- 022: Categories
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_task_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#3B82F6',
    icon TEXT DEFAULT 'task',
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, name)
);

CREATE INDEX IF NOT EXISTS idx_task_categories_owner ON shadow_task_categories(owner_id);

CREATE TABLE IF NOT EXISTS shadow_appointment_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    default_duration INTEGER DEFAULT 60,
    location_type TEXT CHECK (location_type IN ('in_person', 'video_call', 'phone_call', 'other')),
    color TEXT DEFAULT '#10B981',
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, name)
);

CREATE INDEX IF NOT EXISTS idx_appointment_types_owner ON shadow_appointment_types(owner_id);
CREATE INDEX IF NOT EXISTS idx_tasks_category ON shadow_tasks(category_id);
CREATE INDEX IF NOT EXISTS idx_appointments_type ON shadow_appointments(type_id);

-- Add FK constraints (after categories table exists)
ALTER TABLE shadow_tasks DROP CONSTRAINT IF EXISTS shadow_tasks_category_id_fkey;
ALTER TABLE shadow_tasks ADD CONSTRAINT shadow_tasks_category_id_fkey
    FOREIGN KEY (category_id) REFERENCES shadow_task_categories(id);

ALTER TABLE shadow_appointments DROP CONSTRAINT IF EXISTS shadow_appointments_type_id_fkey;
ALTER TABLE shadow_appointments ADD CONSTRAINT shadow_appointments_type_id_fkey
    FOREIGN KEY (type_id) REFERENCES shadow_appointment_types(id);

-- ============================================================================
-- 023: User Settings
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL UNIQUE,
    auto_create_from_conversations BOOLEAN DEFAULT FALSE,
    group_monitoring_enabled BOOLEAN DEFAULT FALSE,
    gcal_check_conflicts BOOLEAN DEFAULT TRUE,
    gcal_auto_sync BOOLEAN DEFAULT TRUE,
    default_reminder_minutes INTEGER DEFAULT 30,
    morning_summary_enabled BOOLEAN DEFAULT FALSE,
    morning_summary_time TIME DEFAULT '07:00',
    always_ask_incomplete BOOLEAN DEFAULT TRUE,
    timezone TEXT DEFAULT 'America/Sao_Paulo',
    language TEXT DEFAULT 'pt-BR',
    use_emojis BOOLEAN DEFAULT TRUE,
    verbose_responses BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shadow_user_settings_owner ON shadow_user_settings(owner_id);

-- ============================================================================
-- 024: Scheduled Alerts
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_scheduled_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    alert_time TIME NOT NULL,
    timezone TEXT DEFAULT 'America/Sao_Paulo',
    recurrence TEXT NOT NULL DEFAULT 'daily' CHECK (recurrence IN ('daily', 'weekly', 'weekdays', 'custom')),
    days_of_week INTEGER[] DEFAULT '{1,2,3,4,5,6,7}',
    alert_type TEXT NOT NULL DEFAULT 'summary' CHECK (alert_type IN ('summary', 'reminder', 'custom')),
    custom_message TEXT,
    include_tasks BOOLEAN DEFAULT TRUE,
    include_appointments BOOLEAN DEFAULT TRUE,
    include_reminders BOOLEAN DEFAULT TRUE,
    include_overdue BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    last_sent_at TIMESTAMPTZ,
    next_scheduled_at TIMESTAMPTZ,
    name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_alerts_owner ON shadow_scheduled_alerts(owner_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_alerts_active ON shadow_scheduled_alerts(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_scheduled_alerts_next ON shadow_scheduled_alerts(next_scheduled_at) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS shadow_alert_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id UUID REFERENCES shadow_scheduled_alerts(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    content TEXT NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_history_alert ON shadow_alert_history(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_owner ON shadow_alert_history(owner_id);

-- ============================================================================
-- 025: Learning System
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    message_id TEXT,
    response_text TEXT,
    rating TEXT NOT NULL CHECK (rating IN ('positive', 'negative', 'correction')),
    correction_text TEXT,
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shadow_feedback_owner ON shadow_feedback(owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_feedback_corrections ON shadow_feedback(owner_id, rating) WHERE rating = 'correction';

CREATE TABLE IF NOT EXISTS shadow_learned_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    trigger_text TEXT,
    trigger_regex TEXT,
    learned_action TEXT NOT NULL,
    tool_name TEXT,
    example_input TEXT,
    example_correction TEXT,
    confidence REAL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    occurrences INTEGER DEFAULT 1,
    last_matched_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shadow_patterns_lookup ON shadow_learned_patterns(owner_id, pattern_type, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_shadow_patterns_tool ON shadow_learned_patterns(owner_id, tool_name, is_active) WHERE is_active = TRUE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_shadow_patterns_unique ON shadow_learned_patterns(owner_id, pattern_type, COALESCE(trigger_text, ''), COALESCE(tool_name, ''));

CREATE TABLE IF NOT EXISTS shadow_user_preferences_learned (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    preference_key TEXT NOT NULL,
    preference_value TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    evidence_count INTEGER DEFAULT 1,
    last_observed_at TIMESTAMPTZ,
    source TEXT DEFAULT 'auto' CHECK (source IN ('auto', 'explicit', 'correction')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, preference_key)
);

-- ============================================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================================

-- Updated_at triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_shadow_cron_jobs_updated_at ON shadow_cron_jobs;
CREATE TRIGGER trigger_shadow_cron_jobs_updated_at BEFORE UPDATE ON shadow_cron_jobs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_shadow_sessions_updated_at ON shadow_sessions;
CREATE TRIGGER trigger_shadow_sessions_updated_at BEFORE UPDATE ON shadow_sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_contact_context_updated ON shadow_contact_context;
CREATE TRIGGER trigger_contact_context_updated BEFORE UPDATE ON shadow_contact_context FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_shadow_user_settings_updated_at ON shadow_user_settings;
CREATE TRIGGER trigger_shadow_user_settings_updated_at BEFORE UPDATE ON shadow_user_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_shadow_scheduled_alerts_updated_at ON shadow_scheduled_alerts;
CREATE TRIGGER trigger_shadow_scheduled_alerts_updated_at BEFORE UPDATE ON shadow_scheduled_alerts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Seed default categories function
CREATE OR REPLACE FUNCTION shadow_seed_default_categories(p_owner_id TEXT)
RETURNS VOID AS $$
BEGIN
    INSERT INTO shadow_task_categories (owner_id, name, color, icon, is_default)
    VALUES
        (p_owner_id, 'pessoal', '#8B5CF6', 'user', TRUE),
        (p_owner_id, 'trabalho', '#3B82F6', 'briefcase', TRUE),
        (p_owner_id, 'compras', '#F59E0B', 'shopping-cart', TRUE),
        (p_owner_id, 'saude', '#EF4444', 'heart', TRUE),
        (p_owner_id, 'financeiro', '#10B981', 'dollar-sign', TRUE),
        (p_owner_id, 'urgente', '#DC2626', 'alert-circle', TRUE)
    ON CONFLICT (owner_id, name) DO NOTHING;

    INSERT INTO shadow_appointment_types (owner_id, name, default_duration, location_type, color, is_default)
    VALUES
        (p_owner_id, 'reuniao', 60, 'video_call', '#3B82F6', TRUE),
        (p_owner_id, 'call', 30, 'phone_call', '#10B981', TRUE),
        (p_owner_id, 'presencial', 60, 'in_person', '#F59E0B', TRUE),
        (p_owner_id, 'entrevista', 45, 'video_call', '#8B5CF6', TRUE),
        (p_owner_id, 'medico', 30, 'in_person', '#EF4444', TRUE),
        (p_owner_id, 'social', 120, 'in_person', '#EC4899', TRUE)
    ON CONFLICT (owner_id, name) DO NOTHING;
END;
$$ LANGUAGE plpgsql;

-- Learning system functions
CREATE OR REPLACE FUNCTION shadow_record_feedback(
    p_owner_id TEXT,
    p_rating TEXT,
    p_response_text TEXT DEFAULT NULL,
    p_correction_text TEXT DEFAULT NULL,
    p_context JSONB DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    v_feedback_id UUID;
BEGIN
    INSERT INTO shadow_feedback (owner_id, rating, response_text, correction_text, context)
    VALUES (p_owner_id, p_rating, p_response_text, p_correction_text, p_context)
    RETURNING id INTO v_feedback_id;
    RETURN v_feedback_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION shadow_learn_pattern(
    p_owner_id TEXT,
    p_pattern_type TEXT,
    p_trigger_text TEXT,
    p_learned_action TEXT,
    p_tool_name TEXT DEFAULT NULL,
    p_confidence_boost REAL DEFAULT 0.1
) RETURNS UUID AS $$
DECLARE
    v_pattern_id UUID;
    v_current_confidence REAL;
    v_current_occurrences INTEGER;
BEGIN
    SELECT id, confidence, occurrences
    INTO v_pattern_id, v_current_confidence, v_current_occurrences
    FROM shadow_learned_patterns
    WHERE owner_id = p_owner_id
      AND pattern_type = p_pattern_type
      AND COALESCE(trigger_text, '') = COALESCE(p_trigger_text, '')
      AND COALESCE(tool_name, '') = COALESCE(p_tool_name, '');

    IF v_pattern_id IS NOT NULL THEN
        UPDATE shadow_learned_patterns
        SET confidence = LEAST(v_current_confidence + p_confidence_boost, 1.0),
            occurrences = v_current_occurrences + 1,
            last_matched_at = NOW(),
            updated_at = NOW()
        WHERE id = v_pattern_id;
    ELSE
        INSERT INTO shadow_learned_patterns (
            owner_id, pattern_type, trigger_text, learned_action, tool_name, confidence
        ) VALUES (
            p_owner_id, p_pattern_type, p_trigger_text, p_learned_action, p_tool_name, 0.5
        )
        RETURNING id INTO v_pattern_id;
    END IF;

    RETURN v_pattern_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION shadow_update_preference(
    p_owner_id TEXT,
    p_key TEXT,
    p_value TEXT,
    p_source TEXT DEFAULT 'auto',
    p_confidence_boost REAL DEFAULT 0.1
) RETURNS VOID AS $$
BEGIN
    INSERT INTO shadow_user_preferences_learned (
        owner_id, preference_key, preference_value, source, confidence
    ) VALUES (
        p_owner_id, p_key, p_value, p_source,
        CASE WHEN p_source = 'explicit' THEN 1.0 ELSE 0.5 END
    )
    ON CONFLICT (owner_id, preference_key) DO UPDATE SET
        preference_value = p_value,
        confidence = CASE
            WHEN EXCLUDED.source = 'explicit' THEN 1.0
            ELSE LEAST(shadow_user_preferences_learned.confidence + p_confidence_boost, 1.0)
        END,
        evidence_count = shadow_user_preferences_learned.evidence_count + 1,
        last_observed_at = NOW(),
        source = CASE WHEN p_source = 'explicit' THEN 'explicit' ELSE shadow_user_preferences_learned.source END,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION shadow_get_patterns(
    p_owner_id TEXT,
    p_min_confidence REAL DEFAULT 0.3
) RETURNS TABLE (
    pattern_type TEXT,
    trigger_text TEXT,
    learned_action TEXT,
    tool_name TEXT,
    confidence REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT slp.pattern_type, slp.trigger_text, slp.learned_action, slp.tool_name, slp.confidence
    FROM shadow_learned_patterns slp
    WHERE slp.owner_id = p_owner_id AND slp.is_active = TRUE AND slp.confidence >= p_min_confidence
    ORDER BY slp.confidence DESC, slp.occurrences DESC;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION shadow_get_learned_preferences(
    p_owner_id TEXT,
    p_min_confidence REAL DEFAULT 0.5
) RETURNS TABLE (
    preference_key TEXT,
    preference_value TEXT,
    confidence REAL,
    source TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT sulp.preference_key, sulp.preference_value, sulp.confidence, sulp.source
    FROM shadow_user_preferences_learned sulp
    WHERE sulp.owner_id = p_owner_id AND sulp.confidence >= p_min_confidence
    ORDER BY sulp.confidence DESC;
END;
$$ LANGUAGE plpgsql;

-- Levenshtein ratio for duplicate detection
CREATE OR REPLACE FUNCTION levenshtein_ratio(s1 TEXT, s2 TEXT)
RETURNS REAL AS $$
DECLARE
    len1 INT := LENGTH(COALESCE(s1, ''));
    len2 INT := LENGTH(COALESCE(s2, ''));
    max_len INT;
BEGIN
    IF len1 = 0 AND len2 = 0 THEN RETURN 1.0; END IF;
    max_len := GREATEST(len1, len2);
    IF max_len = 0 THEN RETURN 1.0; END IF;
    IF LOWER(COALESCE(s1, '')) = LOWER(COALESCE(s2, '')) THEN RETURN 1.0; END IF;
    RETURN 0.5;  -- Simplified - full levenshtein requires fuzzystrmatch extension
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- RLS helper
CREATE OR REPLACE FUNCTION set_shadow_owner(owner_phone TEXT)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.current_owner', owner_phone, true);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- DONE!
-- ============================================================================
-- Total: 27 tables created
-- Run SELECT shadow_seed_default_categories('+5511XXXXXXXXX') after first user creation
