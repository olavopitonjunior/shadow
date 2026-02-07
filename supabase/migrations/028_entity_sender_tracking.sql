-- Migration 028: Add sender tracking to extracted entities
-- Stores the actual sender phone/name for proper contact association
-- This fixes the issue where suggestions show invented phones instead of the real sender

-- Add sender_phone column (E.164 format when available)
ALTER TABLE shadow_extracted_entities ADD COLUMN sender_phone TEXT;

-- Add sender_name column (push name from WhatsApp)
ALTER TABLE shadow_extracted_entities ADD COLUMN sender_name TEXT;

-- Index for efficient contact association
CREATE INDEX IF NOT EXISTS idx_entities_sender ON shadow_extracted_entities(sender_phone);
CREATE INDEX IF NOT EXISTS idx_entities_sender_name ON shadow_extracted_entities(sender_name);
