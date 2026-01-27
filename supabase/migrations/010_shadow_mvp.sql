-- Shadow MVP schema (minimal)
-- Tables needed for webhook + agent MVP

CREATE TABLE IF NOT EXISTS shadow_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone_number TEXT UNIQUE NOT NULL,
  name TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shadow_contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  phone_number TEXT,
  name TEXT NOT NULL,
  company TEXT,
  last_interaction_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, phone_number)
);

CREATE TABLE IF NOT EXISTS shadow_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  started_at TIMESTAMPTZ DEFAULT NOW(),
  last_message_at TIMESTAMPTZ,
  summary TEXT
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
  contact_id UUID REFERENCES shadow_contacts(id),
  title TEXT NOT NULL,
  description TEXT,
  due_date TIMESTAMPTZ,
  status TEXT CHECK (status IN ('pending', 'done', 'cancelled')) DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS shadow_appointments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES shadow_users(id),
  contact_id UUID REFERENCES shadow_contacts(id),
  title TEXT NOT NULL,
  description TEXT,
  scheduled_at TIMESTAMPTZ NOT NULL,
  status TEXT CHECK (status IN ('scheduled', 'completed', 'cancelled')) DEFAULT 'scheduled',
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
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shadow_contacts_user ON shadow_contacts(user_id);
CREATE INDEX IF NOT EXISTS idx_shadow_tasks_user_status ON shadow_tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_shadow_appointments_user_date ON shadow_appointments(user_id, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_shadow_messages_conversation ON shadow_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_shadow_reminders_pending ON shadow_reminders(remind_at) WHERE sent = FALSE;
