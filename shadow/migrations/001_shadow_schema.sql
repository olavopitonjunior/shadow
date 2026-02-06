-- Shadow A.I. - Schema do Banco de Dados
-- Supabase PostgreSQL

-- ===========================================
-- TABELAS PRINCIPAIS
-- ===========================================

-- Organizações (multi-tenancy)
CREATE TABLE shadow_organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  plan TEXT CHECK (plan IN ('free', 'starter', 'professional', 'enterprise')) DEFAULT 'free',
  max_users INT DEFAULT 5,
  billing_email TEXT,
  stripe_customer_id TEXT,
  settings JSONB DEFAULT '{}',
  sharing_settings JSONB DEFAULT '{
    "contacts": "shared",
    "appointments": "team",
    "memories": "shared"
  }',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Usuários do Shadow
CREATE TABLE shadow_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID REFERENCES shadow_organizations(id),
  phone_number TEXT UNIQUE NOT NULL,
  name TEXT,
  whatsapp_type TEXT CHECK (whatsapp_type IN ('personal', 'business')),
  business_api_config JSONB,
  role_in_org TEXT CHECK (role_in_org IN ('owner', 'admin', 'member')) DEFAULT 'member',
  voice_preference TEXT CHECK (voice_preference IN ('text_only', 'audio_only', 'audio_long', 'mirror')) DEFAULT 'audio_long',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contatos extraídos
CREATE TABLE shadow_contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  phone_number TEXT,
  name TEXT NOT NULL,
  company TEXT,
  role TEXT,
  notes TEXT,
  tags TEXT[],
  last_interaction_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, phone_number)
);

-- Tarefas
CREATE TABLE shadow_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  title TEXT NOT NULL,
  description TEXT,
  due_date TIMESTAMPTZ,
  status TEXT CHECK (status IN ('pending', 'done', 'cancelled')) DEFAULT 'pending',
  priority TEXT CHECK (priority IN ('low', 'medium', 'high')) DEFAULT 'medium',
  source_message_id UUID,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- Compromissos/Agenda
CREATE TABLE shadow_appointments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  title TEXT NOT NULL,
  description TEXT,
  scheduled_at TIMESTAMPTZ NOT NULL,
  duration_minutes INT DEFAULT 60,
  location TEXT,
  status TEXT CHECK (status IN ('scheduled', 'completed', 'cancelled')) DEFAULT 'scheduled',
  reminder_sent BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Histórico de conversas (com clientes)
CREATE TABLE shadow_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  chat_id TEXT,
  chat_type TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  last_message_at TIMESTAMPTZ,
  summary TEXT,
  sentiment TEXT CHECK (sentiment IN ('positive', 'neutral', 'negative')),
  topics TEXT[]
);

-- Mensagens individuais
CREATE TABLE shadow_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES shadow_conversations(id),
  direction TEXT CHECK (direction IN ('inbound', 'outbound')) NOT NULL,
  content TEXT NOT NULL,
  content_type TEXT CHECK (content_type IN ('text', 'audio', 'image', 'document')) DEFAULT 'text',
  audio_transcription TEXT,
  extracted_entities JSONB,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Interações usuário <-> Shadow
CREATE TABLE shadow_interactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  user_message TEXT NOT NULL,
  shadow_response TEXT NOT NULL,
  intent TEXT,
  entities_created JSONB,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Lembretes agendados
CREATE TABLE shadow_reminders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  task_id UUID REFERENCES shadow_tasks(id),
  appointment_id UUID REFERENCES shadow_appointments(id),
  remind_at TIMESTAMPTZ NOT NULL,
  message TEXT NOT NULL,
  sent BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ===========================================
-- SISTEMA DE MEMÓRIA
-- ===========================================

-- Memórias estruturadas por contato
CREATE TABLE shadow_memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  memory_type TEXT CHECK (memory_type IN ('fact', 'preference', 'negotiation', 'context')),
  content TEXT NOT NULL,
  confidence FLOAT DEFAULT 1.0,
  source_message_id UUID,
  extracted_at TIMESTAMPTZ DEFAULT NOW(),
  valid_until TIMESTAMPTZ,
  is_active BOOLEAN DEFAULT TRUE
);

-- Embeddings para busca semântica
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE shadow_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  source_type TEXT CHECK (source_type IN ('message', 'memory', 'summary')),
  source_id UUID NOT NULL,
  embedding vector(1536),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Resumos compactados de conversas antigas
CREATE TABLE shadow_conversation_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES shadow_conversations(id),
  summary TEXT NOT NULL,
  key_facts JSONB,
  messages_from TIMESTAMPTZ,
  messages_to TIMESTAMPTZ,
  message_count INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ===========================================
-- GRUPOS WHATSAPP
-- ===========================================

CREATE TABLE shadow_group_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  group_jid TEXT NOT NULL,
  group_name TEXT,
  group_type TEXT CHECK (group_type IN ('client', 'internal', 'support', 'unknown')),
  should_monitor BOOLEAN DEFAULT FALSE,
  participants JSONB,
  primary_contact_id UUID REFERENCES shadow_contacts(id),
  UNIQUE(user_id, group_jid)
);

-- ===========================================
-- INTEGRAÇÕES EXTERNAS
-- ===========================================

CREATE TABLE shadow_integrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  organization_id UUID REFERENCES shadow_organizations(id),
  provider TEXT NOT NULL,
  access_token TEXT,
  refresh_token TEXT,
  token_expires_at TIMESTAMPTZ,
  config JSONB,
  is_active BOOLEAN DEFAULT TRUE,
  last_sync_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, provider)
);

CREATE TABLE shadow_entity_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  integration_id UUID REFERENCES shadow_integrations(id),
  local_type TEXT,
  local_id UUID,
  external_type TEXT,
  external_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(integration_id, local_type, local_id)
);

-- ===========================================
-- ONBOARDING
-- ===========================================

CREATE TABLE shadow_onboarding_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone_number TEXT UNIQUE NOT NULL,
  state TEXT NOT NULL DEFAULT 'not_started',
  data JSONB DEFAULT '{}',
  started_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);

-- ===========================================
-- ANALYTICS
-- ===========================================

CREATE TABLE shadow_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID REFERENCES shadow_organizations(id),
  user_id UUID REFERENCES shadow_users(id),
  event_type TEXT NOT NULL,
  event_data JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE shadow_daily_stats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID REFERENCES shadow_organizations(id),
  user_id UUID REFERENCES shadow_users(id),
  date DATE NOT NULL,
  messages_received INT DEFAULT 0,
  tasks_completed INT DEFAULT 0,
  contacts_created INT DEFAULT 0,
  UNIQUE(organization_id, user_id, date)
);

-- ===========================================
-- ÍNDICES
-- ===========================================

CREATE INDEX idx_shadow_contacts_user ON shadow_contacts(user_id);
CREATE INDEX idx_shadow_contacts_org ON shadow_contacts(organization_id);
CREATE INDEX idx_shadow_tasks_user_status ON shadow_tasks(user_id, status);
CREATE INDEX idx_shadow_tasks_org ON shadow_tasks(organization_id);
CREATE INDEX idx_shadow_appointments_user_date ON shadow_appointments(user_id, scheduled_at);
CREATE INDEX idx_shadow_appointments_org ON shadow_appointments(organization_id);
CREATE INDEX idx_shadow_messages_conversation ON shadow_messages(conversation_id);
CREATE INDEX idx_shadow_reminders_pending ON shadow_reminders(remind_at) WHERE sent = FALSE;
CREATE INDEX idx_shadow_memories_contact ON shadow_memories(contact_id) WHERE is_active = TRUE;
CREATE INDEX idx_shadow_events_org_type ON shadow_events(organization_id, event_type);
CREATE INDEX idx_shadow_events_created ON shadow_events(created_at);

-- Índice para busca vetorial
CREATE INDEX idx_shadow_embeddings_vector ON shadow_embeddings
  USING ivfflat (embedding vector_cosine_ops);

-- ===========================================
-- ROW LEVEL SECURITY
-- ===========================================

ALTER TABLE shadow_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_group_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_integrations ENABLE ROW LEVEL SECURITY;

-- Policies serão criadas conforme necessário durante a implementação

-- ===========================================
-- VIEW DE MÉTRICAS
-- ===========================================

CREATE VIEW shadow_onboarding_funnel AS
SELECT
  DATE(started_at) as date,
  COUNT(*) as started,
  COUNT(*) FILTER (WHERE state = 'completed') as completed,
  CASE
    WHEN COUNT(*) > 0 THEN ROUND(100.0 * COUNT(*) FILTER (WHERE state = 'completed') / COUNT(*), 1)
    ELSE 0
  END as conversion_rate
FROM shadow_onboarding_sessions
GROUP BY DATE(started_at);
