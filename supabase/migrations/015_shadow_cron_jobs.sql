-- Migration: shadow_cron_jobs
-- Tabela para persistir jobs agendados do CronService

CREATE TABLE IF NOT EXISTS shadow_cron_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES shadow_users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES shadow_organizations(id) ON DELETE CASCADE,

    -- Identificação
    name TEXT NOT NULL,
    description TEXT,

    -- Agendamento
    schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('at', 'every', 'cron')),
    schedule_at_ms BIGINT,           -- Timestamp para kind='at'
    schedule_every_ms BIGINT,        -- Intervalo para kind='every'
    schedule_anchor_ms BIGINT,       -- Âncora para kind='every'
    schedule_expr TEXT,              -- Expressão cron para kind='cron'
    schedule_tz TEXT DEFAULT 'America/Sao_Paulo',

    -- Ação
    action TEXT NOT NULL,            -- 'send_reminder', 'daily_summary', etc.
    params JSONB DEFAULT '{}',       -- Parâmetros da ação

    -- Controle
    enabled BOOLEAN DEFAULT true,
    delete_after_run BOOLEAN DEFAULT false,

    -- Estado
    state_next_run_at_ms BIGINT,
    state_running_at_ms BIGINT,
    state_last_run_at_ms BIGINT,
    state_last_status TEXT CHECK (state_last_status IN ('ok', 'error', 'skipped')),
    state_last_error TEXT,
    state_last_duration_ms BIGINT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_shadow_cron_jobs_user ON shadow_cron_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_shadow_cron_jobs_enabled ON shadow_cron_jobs(enabled) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_shadow_cron_jobs_next_run ON shadow_cron_jobs(state_next_run_at_ms) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_shadow_cron_jobs_action ON shadow_cron_jobs(action);

-- Trigger para atualizar updated_at
CREATE OR REPLACE FUNCTION update_shadow_cron_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_shadow_cron_jobs_updated_at ON shadow_cron_jobs;
CREATE TRIGGER trigger_shadow_cron_jobs_updated_at
    BEFORE UPDATE ON shadow_cron_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_shadow_cron_jobs_updated_at();

-- Comentários
COMMENT ON TABLE shadow_cron_jobs IS 'Jobs agendados do CronService';
COMMENT ON COLUMN shadow_cron_jobs.schedule_kind IS 'Tipo de agendamento: at (único), every (intervalo), cron (expressão)';
COMMENT ON COLUMN shadow_cron_jobs.action IS 'Ação a executar: send_reminder, daily_summary, follow_up, etc.';
