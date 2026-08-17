-- Migration 030: Multi-Tenant Core
-- Add owner_id to tasks, appointments, reminders, contacts for per-user data isolation.
-- SQLite equivalent is handled by _ensure_schema() PRAGMA table_info checks in sqlite_storage.py.

-- Tasks
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS owner_id TEXT;
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_id);

-- Appointments
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS owner_id TEXT;
CREATE INDEX IF NOT EXISTS idx_appointments_owner ON appointments(owner_id);

-- Reminders
ALTER TABLE reminders ADD COLUMN IF NOT EXISTS owner_id TEXT;
CREATE INDEX IF NOT EXISTS idx_reminders_owner ON reminders(owner_id);

-- Contacts (SQLite only - Supabase shadow_contacts already has user_id)
-- ALTER TABLE contacts ADD COLUMN IF NOT EXISTS owner_id TEXT;
-- CREATE INDEX IF NOT EXISTS idx_contacts_owner ON contacts(owner_id);
