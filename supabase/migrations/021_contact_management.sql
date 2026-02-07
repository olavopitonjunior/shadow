-- Migration: Advanced Contact Management
-- Phase 1: CRUD completo, soft delete, merge, duplicatas

-- =====================================================
-- SOFT DELETE for contacts
-- =====================================================
ALTER TABLE shadow_contacts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE shadow_contacts ADD COLUMN IF NOT EXISTS deleted_by TEXT;

COMMENT ON COLUMN shadow_contacts.deleted_at IS 'Soft delete timestamp';
COMMENT ON COLUMN shadow_contacts.deleted_by IS 'Who deleted the contact (owner phone)';

-- Index for excluding deleted contacts
CREATE INDEX IF NOT EXISTS idx_shadow_contacts_active
ON shadow_contacts(user_id) WHERE deleted_at IS NULL;

-- =====================================================
-- SOFT DELETE for contact_context
-- =====================================================
ALTER TABLE shadow_contact_context ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_contact_context_active
ON shadow_contact_context(owner_id) WHERE deleted_at IS NULL;

-- =====================================================
-- MERGE HISTORY - Track contact merges
-- =====================================================
CREATE TABLE IF NOT EXISTS shadow_contact_merges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    target_phone TEXT NOT NULL,
    source_phone TEXT NOT NULL,
    source_name TEXT,
    merged_at TIMESTAMPTZ DEFAULT NOW(),
    merged_by TEXT
);

COMMENT ON TABLE shadow_contact_merges IS 'History of contact merges for audit/undo';
COMMENT ON COLUMN shadow_contact_merges.target_phone IS 'Contact that was kept';
COMMENT ON COLUMN shadow_contact_merges.source_phone IS 'Contact that was merged into target';

CREATE INDEX IF NOT EXISTS idx_contact_merges_owner ON shadow_contact_merges(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_merges_target ON shadow_contact_merges(target_phone);

-- =====================================================
-- DUPLICATE DETECTION - Similarity scores
-- =====================================================
-- Note: Full duplicate detection runs in application code
-- This table stores known duplicates/non-duplicates for training

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

COMMENT ON TABLE shadow_contact_duplicates IS 'Detected duplicate contacts awaiting resolution';
COMMENT ON COLUMN shadow_contact_duplicates.similarity_score IS 'Name similarity score 0-1';
COMMENT ON COLUMN shadow_contact_duplicates.status IS 'pending, confirmed (are duplicates), rejected (not duplicates), merged';

CREATE INDEX IF NOT EXISTS idx_contact_duplicates_owner ON shadow_contact_duplicates(owner_id);
CREATE INDEX IF NOT EXISTS idx_contact_duplicates_pending ON shadow_contact_duplicates(owner_id, status) WHERE status = 'pending';

-- =====================================================
-- FUNCTIONS for duplicate detection
-- =====================================================

-- Levenshtein distance function for name similarity
CREATE OR REPLACE FUNCTION levenshtein_ratio(s1 TEXT, s2 TEXT)
RETURNS REAL AS $$
DECLARE
    len1 INT := LENGTH(COALESCE(s1, ''));
    len2 INT := LENGTH(COALESCE(s2, ''));
    max_len INT;
    distance INT;
BEGIN
    IF len1 = 0 AND len2 = 0 THEN
        RETURN 1.0;
    END IF;

    max_len := GREATEST(len1, len2);
    IF max_len = 0 THEN
        RETURN 1.0;
    END IF;

    -- Use built-in levenshtein if fuzzystrmatch extension is available
    BEGIN
        distance := levenshtein(LOWER(COALESCE(s1, '')), LOWER(COALESCE(s2, '')));
        RETURN 1.0 - (distance::REAL / max_len::REAL);
    EXCEPTION WHEN undefined_function THEN
        -- Fallback: simple equality check
        IF LOWER(COALESCE(s1, '')) = LOWER(COALESCE(s2, '')) THEN
            RETURN 1.0;
        ELSE
            RETURN 0.0;
        END IF;
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function to find potential duplicates for a contact
CREATE OR REPLACE FUNCTION find_contact_duplicates(
    p_owner_id TEXT,
    p_phone TEXT,
    p_name TEXT,
    p_threshold REAL DEFAULT 0.8
)
RETURNS TABLE(
    contact_phone TEXT,
    contact_name TEXT,
    similarity REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.contact_phone,
        cc.contact_name,
        levenshtein_ratio(p_name, cc.contact_name) as similarity
    FROM shadow_contact_context cc
    WHERE cc.owner_id = p_owner_id
      AND cc.contact_phone != p_phone
      AND cc.deleted_at IS NULL
      AND levenshtein_ratio(p_name, cc.contact_name) >= p_threshold
    ORDER BY similarity DESC
    LIMIT 10;
END;
$$ LANGUAGE plpgsql;
