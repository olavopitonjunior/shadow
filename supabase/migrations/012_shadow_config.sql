-- Shadow config (singleton)

CREATE TABLE IF NOT EXISTS shadow_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_phone TEXT,
  ignore_groups BOOLEAN DEFAULT TRUE,
  store_relevant_only BOOLEAN DEFAULT TRUE,
  enable_shadow_replies BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure single row
INSERT INTO shadow_config (owner_phone)
SELECT NULL
WHERE NOT EXISTS (SELECT 1 FROM shadow_config);
