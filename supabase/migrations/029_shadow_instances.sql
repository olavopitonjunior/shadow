-- Migration 029: Shadow Instances
-- Manages multiple Shadow instances for multi-tenant deployments
-- Each instance represents a WhatsApp connection with its own session

CREATE TABLE IF NOT EXISTS shadow_instances (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    owner_e164 TEXT,
    gateway_user_id TEXT NOT NULL UNIQUE,
    status TEXT DEFAULT 'disconnected',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    connected_at TIMESTAMPTZ,
    disconnected_at TIMESTAMPTZ
);

-- Index for fast lookup by gateway_user_id
CREATE INDEX IF NOT EXISTS idx_shadow_instances_gateway_user_id ON shadow_instances(gateway_user_id);

-- Index for status queries
CREATE INDEX IF NOT EXISTS idx_shadow_instances_status ON shadow_instances(status);

-- Index for owner lookup
CREATE INDEX IF NOT EXISTS idx_shadow_instances_owner ON shadow_instances(owner_e164);

-- Comments for documentation
COMMENT ON TABLE shadow_instances IS 'Tracks Shadow instances for multi-tenant deployments';
COMMENT ON COLUMN shadow_instances.id IS 'Unique instance identifier';
COMMENT ON COLUMN shadow_instances.name IS 'Display name for the instance';
COMMENT ON COLUMN shadow_instances.phone IS 'WhatsApp phone number (when connected)';
COMMENT ON COLUMN shadow_instances.owner_e164 IS 'Owner phone in E.164 format';
COMMENT ON COLUMN shadow_instances.gateway_user_id IS 'Unique gateway user ID for this instance';
COMMENT ON COLUMN shadow_instances.status IS 'Connection status: disconnected, connecting, connected';
COMMENT ON COLUMN shadow_instances.created_at IS 'When the instance was created';
COMMENT ON COLUMN shadow_instances.connected_at IS 'Last successful connection timestamp';
COMMENT ON COLUMN shadow_instances.disconnected_at IS 'Last disconnection timestamp';
