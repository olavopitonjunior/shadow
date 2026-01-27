-- Shadow webhook logs (debugging)

CREATE TABLE IF NOT EXISTS shadow_webhook_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT,
  user_phone TEXT,
  contact_phone TEXT,
  direction TEXT,
  content TEXT,
  content_type TEXT,
  is_group BOOLEAN,
  received_at TIMESTAMPTZ DEFAULT NOW(),
  payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_shadow_webhook_logs_received_at
  ON shadow_webhook_logs(received_at DESC);
