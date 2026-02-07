-- Phase 2: Task Categories and Appointment Types
-- ================================================

-- Task Categories table
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

-- Appointment Types table
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

-- Add category/type columns to existing tables
ALTER TABLE shadow_tasks ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES shadow_task_categories(id);
ALTER TABLE shadow_tasks ADD COLUMN IF NOT EXISTS priority TEXT DEFAULT 'normal';

ALTER TABLE shadow_appointments ADD COLUMN IF NOT EXISTS type_id UUID REFERENCES shadow_appointment_types(id);
ALTER TABLE shadow_appointments ADD COLUMN IF NOT EXISTS location TEXT;
ALTER TABLE shadow_appointments ADD COLUMN IF NOT EXISTS video_link TEXT;

-- Create indexes for the new foreign keys
CREATE INDEX IF NOT EXISTS idx_tasks_category ON shadow_tasks(category_id);
CREATE INDEX IF NOT EXISTS idx_appointments_type ON shadow_appointments(type_id);

-- Function to insert default categories for a new owner
CREATE OR REPLACE FUNCTION shadow_seed_default_categories(p_owner_id TEXT)
RETURNS VOID AS $$
BEGIN
    -- Default task categories
    INSERT INTO shadow_task_categories (owner_id, name, color, icon, is_default)
    VALUES
        (p_owner_id, 'pessoal', '#8B5CF6', 'user', TRUE),
        (p_owner_id, 'trabalho', '#3B82F6', 'briefcase', TRUE),
        (p_owner_id, 'compras', '#F59E0B', 'shopping-cart', TRUE),
        (p_owner_id, 'saude', '#EF4444', 'heart', TRUE),
        (p_owner_id, 'financeiro', '#10B981', 'dollar-sign', TRUE),
        (p_owner_id, 'urgente', '#DC2626', 'alert-circle', TRUE)
    ON CONFLICT (owner_id, name) DO NOTHING;

    -- Default appointment types
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

-- Comment explaining usage
COMMENT ON FUNCTION shadow_seed_default_categories IS
'Seeds default task categories and appointment types for a new owner.
Call this when a new user is created: SELECT shadow_seed_default_categories(owner_phone);';
