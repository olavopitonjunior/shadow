-- Migration: Add retry tracking columns to shadow_reminders
-- Inspired by moltbot cron delivery system

-- Adiciona colunas para tracking de tentativas
ALTER TABLE shadow_reminders
  ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_error TEXT,
  ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS failed BOOLEAN DEFAULT FALSE;

-- Índice para encontrar reminders que falharam permanentemente
CREATE INDEX IF NOT EXISTS idx_shadow_reminders_failed
  ON shadow_reminders (failed)
  WHERE failed = TRUE;

-- Atualiza o índice de pendentes para excluir falhas permanentes
DROP INDEX IF EXISTS idx_shadow_reminders_pending;
CREATE INDEX idx_shadow_reminders_pending
  ON shadow_reminders (remind_at)
  WHERE sent = FALSE AND failed = FALSE;

-- Comentários para documentação
COMMENT ON COLUMN shadow_reminders.attempts IS 'Total de tentativas de envio';
COMMENT ON COLUMN shadow_reminders.last_error IS 'Último erro de envio';
COMMENT ON COLUMN shadow_reminders.sent_at IS 'Timestamp de envio bem-sucedido';
COMMENT ON COLUMN shadow_reminders.failed IS 'True se atingiu máximo de tentativas sem sucesso';
