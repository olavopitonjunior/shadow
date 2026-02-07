-- Migration 025: Shadow Learning System
-- Implements feedback loop and correction-based learning inspired by OpenClaw

-- ============================================================================
-- Feedback Table: User ratings on responses
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    message_id TEXT,                    -- Optional reference to original message
    response_text TEXT,                 -- The response that was rated
    rating TEXT NOT NULL CHECK (rating IN ('positive', 'negative', 'correction')),
    correction_text TEXT,               -- If rating='correction', what should have been done
    context JSONB DEFAULT '{}',         -- Additional context (tool used, params, etc.)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for querying user feedback
CREATE INDEX IF NOT EXISTS idx_shadow_feedback_owner
ON shadow_feedback(owner_id, created_at DESC);

-- Index for finding corrections (for learning)
CREATE INDEX IF NOT EXISTS idx_shadow_feedback_corrections
ON shadow_feedback(owner_id, rating)
WHERE rating = 'correction';

-- ============================================================================
-- Learned Patterns Table: What Shadow has learned from user corrections
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_learned_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    pattern_type TEXT NOT NULL,         -- 'missing_date', 'wrong_contact', 'wrong_category', etc.
    trigger_text TEXT,                  -- Pattern that caused the problem (normalized)
    trigger_regex TEXT,                 -- Optional regex for matching
    learned_action TEXT NOT NULL,       -- What to do differently
    tool_name TEXT,                     -- Which tool this applies to
    example_input TEXT,                 -- Example that triggered learning
    example_correction TEXT,            -- What the correction was
    confidence REAL DEFAULT 0.5,        -- How confident we are (0.0-1.0)
    occurrences INTEGER DEFAULT 1,      -- How many times this pattern matched
    last_matched_at TIMESTAMPTZ,        -- Last time this pattern was used
    is_active BOOLEAN DEFAULT TRUE,     -- Can be disabled if wrong
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for pattern lookup
CREATE INDEX IF NOT EXISTS idx_shadow_patterns_lookup
ON shadow_learned_patterns(owner_id, pattern_type, is_active)
WHERE is_active = TRUE;

-- Index for tool-specific patterns
CREATE INDEX IF NOT EXISTS idx_shadow_patterns_tool
ON shadow_learned_patterns(owner_id, tool_name, is_active)
WHERE is_active = TRUE;

-- Unique constraint to avoid duplicate patterns
CREATE UNIQUE INDEX IF NOT EXISTS idx_shadow_patterns_unique
ON shadow_learned_patterns(owner_id, pattern_type, COALESCE(trigger_text, ''), COALESCE(tool_name, ''));

-- ============================================================================
-- User Preferences Learned: Automatically detected preferences
-- ============================================================================
CREATE TABLE IF NOT EXISTS shadow_user_preferences_learned (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,
    preference_key TEXT NOT NULL,       -- 'preferred_meeting_time', 'default_priority', etc.
    preference_value TEXT NOT NULL,     -- The learned value
    confidence REAL DEFAULT 0.5,        -- Confidence based on occurrences
    evidence_count INTEGER DEFAULT 1,   -- How many times we observed this
    last_observed_at TIMESTAMPTZ,
    source TEXT DEFAULT 'auto',         -- 'auto' (learned), 'explicit' (user said), 'correction'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, preference_key)
);

-- ============================================================================
-- Functions for Learning
-- ============================================================================

-- Function to record feedback and potentially create a learned pattern
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
    -- Insert feedback
    INSERT INTO shadow_feedback (owner_id, rating, response_text, correction_text, context)
    VALUES (p_owner_id, p_rating, p_response_text, p_correction_text, p_context)
    RETURNING id INTO v_feedback_id;

    RETURN v_feedback_id;
END;
$$ LANGUAGE plpgsql;

-- Function to update or insert a learned pattern
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
    -- Check if pattern already exists
    SELECT id, confidence, occurrences
    INTO v_pattern_id, v_current_confidence, v_current_occurrences
    FROM shadow_learned_patterns
    WHERE owner_id = p_owner_id
      AND pattern_type = p_pattern_type
      AND COALESCE(trigger_text, '') = COALESCE(p_trigger_text, '')
      AND COALESCE(tool_name, '') = COALESCE(p_tool_name, '');

    IF v_pattern_id IS NOT NULL THEN
        -- Update existing pattern
        UPDATE shadow_learned_patterns
        SET confidence = LEAST(v_current_confidence + p_confidence_boost, 1.0),
            occurrences = v_current_occurrences + 1,
            last_matched_at = NOW(),
            updated_at = NOW()
        WHERE id = v_pattern_id;
    ELSE
        -- Insert new pattern
        INSERT INTO shadow_learned_patterns (
            owner_id, pattern_type, trigger_text, learned_action,
            tool_name, confidence
        ) VALUES (
            p_owner_id, p_pattern_type, p_trigger_text, p_learned_action,
            p_tool_name, 0.5
        )
        RETURNING id INTO v_pattern_id;
    END IF;

    RETURN v_pattern_id;
END;
$$ LANGUAGE plpgsql;

-- Function to update learned preference
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
        source = CASE
            WHEN p_source = 'explicit' THEN 'explicit'
            ELSE shadow_user_preferences_learned.source
        END,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Function to get active patterns for a user
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
    SELECT
        slp.pattern_type,
        slp.trigger_text,
        slp.learned_action,
        slp.tool_name,
        slp.confidence
    FROM shadow_learned_patterns slp
    WHERE slp.owner_id = p_owner_id
      AND slp.is_active = TRUE
      AND slp.confidence >= p_min_confidence
    ORDER BY slp.confidence DESC, slp.occurrences DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to get learned preferences for a user
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
    SELECT
        sulp.preference_key,
        sulp.preference_value,
        sulp.confidence,
        sulp.source
    FROM shadow_user_preferences_learned sulp
    WHERE sulp.owner_id = p_owner_id
      AND sulp.confidence >= p_min_confidence
    ORDER BY sulp.confidence DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON TABLE shadow_feedback IS 'User feedback on Shadow responses (positive, negative, correction)';
COMMENT ON TABLE shadow_learned_patterns IS 'Patterns learned from user corrections to improve future responses';
COMMENT ON TABLE shadow_user_preferences_learned IS 'Automatically learned user preferences from behavior patterns';

COMMENT ON COLUMN shadow_learned_patterns.pattern_type IS 'Type: missing_date, wrong_contact, wrong_category, ambiguous_task, etc.';
COMMENT ON COLUMN shadow_learned_patterns.trigger_text IS 'Normalized text pattern that triggers this rule';
COMMENT ON COLUMN shadow_learned_patterns.learned_action IS 'Action to take: ask_date, confirm_contact, suggest_category, etc.';
COMMENT ON COLUMN shadow_learned_patterns.confidence IS 'Confidence 0-1, increases with each occurrence';
