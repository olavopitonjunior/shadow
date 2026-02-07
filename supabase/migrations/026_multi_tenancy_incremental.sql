-- =============================================
-- Migration 026: Multi-Tenancy Incremental
-- =============================================
-- This migration adds incremental multi-tenancy support:
-- 1. Helper function to resolve phone → user_id
-- 2. Optional user_id columns for SaaS future (without removing owner_id)
--
-- MVP mode: Continue using owner_id TEXT as primary identifier
-- SaaS mode: Use user_id UUID via shadow_users table
-- =============================================

-- Helper function to resolve phone number to user_id
-- Returns the UUID of the user with the given phone number
CREATE OR REPLACE FUNCTION shadow_get_user_id(phone TEXT)
RETURNS UUID AS $$
  SELECT id FROM shadow_users WHERE phone_number = phone LIMIT 1;
$$ LANGUAGE sql STABLE;

-- Add user_id column to main tables (optional, for SaaS future)
-- These columns are nullable and don't affect MVP operation
-- shadow_tasks
ALTER TABLE shadow_tasks
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES shadow_users(id);

-- shadow_appointments
ALTER TABLE shadow_appointments
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES shadow_users(id);

-- shadow_reminders
ALTER TABLE shadow_reminders
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES shadow_users(id);

-- shadow_contacts
ALTER TABLE shadow_contacts
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES shadow_users(id);

-- shadow_sessions
ALTER TABLE shadow_sessions
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES shadow_users(id);

-- shadow_user_settings
ALTER TABLE shadow_user_settings
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES shadow_users(id);

-- shadow_scheduled_alerts
ALTER TABLE shadow_scheduled_alerts
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES shadow_users(id);

-- shadow_feedback
ALTER TABLE shadow_feedback
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES shadow_users(id);

-- Create index on user_id for faster lookups (when populated)
CREATE INDEX IF NOT EXISTS idx_shadow_tasks_user_id
ON shadow_tasks(user_id) WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_shadow_appointments_user_id
ON shadow_appointments(user_id) WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_shadow_reminders_user_id
ON shadow_reminders(user_id) WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_shadow_contacts_user_id
ON shadow_contacts(user_id) WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_shadow_sessions_user_id
ON shadow_sessions(user_id) WHERE user_id IS NOT NULL;

-- Helper function to populate user_id from owner_id (for migration)
-- Call this manually when ready to migrate to SaaS mode
CREATE OR REPLACE FUNCTION shadow_populate_user_ids()
RETURNS TABLE(table_name TEXT, updated_count INTEGER) AS $$
DECLARE
  cnt INTEGER;
BEGIN
  -- Tasks
  UPDATE shadow_tasks t
  SET user_id = shadow_get_user_id(t.owner_id)
  WHERE t.user_id IS NULL AND t.owner_id IS NOT NULL;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  table_name := 'shadow_tasks'; updated_count := cnt;
  RETURN NEXT;

  -- Appointments
  UPDATE shadow_appointments a
  SET user_id = shadow_get_user_id(a.owner_id)
  WHERE a.user_id IS NULL AND a.owner_id IS NOT NULL;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  table_name := 'shadow_appointments'; updated_count := cnt;
  RETURN NEXT;

  -- Reminders
  UPDATE shadow_reminders r
  SET user_id = shadow_get_user_id(r.owner_id)
  WHERE r.user_id IS NULL AND r.owner_id IS NOT NULL;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  table_name := 'shadow_reminders'; updated_count := cnt;
  RETURN NEXT;

  -- Contacts
  UPDATE shadow_contacts c
  SET user_id = shadow_get_user_id(c.owner_id)
  WHERE c.user_id IS NULL AND c.owner_id IS NOT NULL;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  table_name := 'shadow_contacts'; updated_count := cnt;
  RETURN NEXT;

  -- Sessions
  UPDATE shadow_sessions s
  SET user_id = shadow_get_user_id(s.owner_id)
  WHERE s.user_id IS NULL AND s.owner_id IS NOT NULL;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  table_name := 'shadow_sessions'; updated_count := cnt;
  RETURN NEXT;

  -- User Settings
  UPDATE shadow_user_settings us
  SET user_id = shadow_get_user_id(us.owner_id)
  WHERE us.user_id IS NULL AND us.owner_id IS NOT NULL;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  table_name := 'shadow_user_settings'; updated_count := cnt;
  RETURN NEXT;

  -- Scheduled Alerts
  UPDATE shadow_scheduled_alerts sa
  SET user_id = shadow_get_user_id(sa.owner_id)
  WHERE sa.user_id IS NULL AND sa.owner_id IS NOT NULL;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  table_name := 'shadow_scheduled_alerts'; updated_count := cnt;
  RETURN NEXT;

  -- Feedback
  UPDATE shadow_feedback f
  SET user_id = shadow_get_user_id(f.owner_id)
  WHERE f.user_id IS NULL AND f.owner_id IS NOT NULL;
  GET DIAGNOSTICS cnt = ROW_COUNT;
  table_name := 'shadow_feedback'; updated_count := cnt;
  RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- Comment explaining the migration strategy
COMMENT ON FUNCTION shadow_get_user_id IS
'Resolves phone number to user_id for multi-tenancy. MVP uses owner_id TEXT, SaaS uses user_id UUID.';

COMMENT ON FUNCTION shadow_populate_user_ids IS
'Populates user_id columns from owner_id. Call manually when ready to migrate from MVP to SaaS mode.';
