ALTER TABLE shadow_config
  ADD COLUMN IF NOT EXISTS evolution_api_url TEXT,
  ADD COLUMN IF NOT EXISTS evolution_api_key TEXT,
  ADD COLUMN IF NOT EXISTS evolution_instance_id TEXT;
