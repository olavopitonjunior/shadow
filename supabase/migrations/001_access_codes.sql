-- Shadow access codes (admin authentication)

CREATE TABLE IF NOT EXISTS access_codes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code VARCHAR(20) UNIQUE NOT NULL,
  role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'user')),
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_access_codes_code ON access_codes(code);

INSERT INTO access_codes (code, role)
SELECT 'ADMIN001', 'admin'
WHERE NOT EXISTS (
  SELECT 1 FROM access_codes WHERE code = 'ADMIN001'
);
