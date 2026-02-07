-- Migration: Add recipient resolution support to shadow_reminders
-- Phase 4: Recipient Resolution (moltbot pattern)

-- Add target_phone column for explicit recipient targeting
ALTER TABLE shadow_reminders
ADD COLUMN IF NOT EXISTS target_phone TEXT;

-- Add recipient_source to track how recipient was resolved
ALTER TABLE shadow_reminders
ADD COLUMN IF NOT EXISTS recipient_source TEXT;

-- Comment explaining the columns
COMMENT ON COLUMN shadow_reminders.target_phone IS 'Explicit target phone for this reminder (overrides config.owner_phone)';
COMMENT ON COLUMN shadow_reminders.recipient_source IS 'How recipient was resolved: explicit, reminder_target, session, config, allowlist';

-- Index for queries by target
CREATE INDEX IF NOT EXISTS idx_shadow_reminders_target_phone
ON shadow_reminders(target_phone)
WHERE target_phone IS NOT NULL;
