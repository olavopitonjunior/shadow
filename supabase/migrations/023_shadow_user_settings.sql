-- Migration 023: Shadow User Settings
-- Centralized user settings for controlling agent behavior

CREATE TABLE IF NOT EXISTS shadow_user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL UNIQUE,

    -- Extração automática de conversas
    auto_create_from_conversations BOOLEAN DEFAULT FALSE,  -- Se true, cria sem perguntar

    -- Monitoramento de grupos
    group_monitoring_enabled BOOLEAN DEFAULT FALSE,  -- Opt-in global

    -- Integração Google Calendar (futuro)
    gcal_check_conflicts BOOLEAN DEFAULT TRUE,  -- Sempre verificar conflitos
    gcal_auto_sync BOOLEAN DEFAULT TRUE,  -- Sincronizar automaticamente

    -- Alertas e lembretes
    default_reminder_minutes INTEGER DEFAULT 30,  -- Antecedência padrão
    morning_summary_enabled BOOLEAN DEFAULT FALSE,
    morning_summary_time TIME DEFAULT '07:00',

    -- Comportamento do agente
    always_ask_incomplete BOOLEAN DEFAULT TRUE,  -- Perguntar quando incompleto
    timezone TEXT DEFAULT 'America/Sao_Paulo',

    -- Preferências de comunicação
    language TEXT DEFAULT 'pt-BR',
    use_emojis BOOLEAN DEFAULT TRUE,
    verbose_responses BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookup by owner
CREATE INDEX IF NOT EXISTS idx_shadow_user_settings_owner ON shadow_user_settings(owner_id);

-- Trigger para atualizar updated_at automaticamente
CREATE OR REPLACE FUNCTION update_shadow_user_settings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_shadow_user_settings_updated_at ON shadow_user_settings;
CREATE TRIGGER trigger_shadow_user_settings_updated_at
    BEFORE UPDATE ON shadow_user_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_shadow_user_settings_updated_at();

-- Comentários para documentação
COMMENT ON TABLE shadow_user_settings IS 'Configurações personalizadas do usuário para o Shadow';
COMMENT ON COLUMN shadow_user_settings.auto_create_from_conversations IS 'Se true, cria tarefas/compromissos automaticamente de conversas sem perguntar';
COMMENT ON COLUMN shadow_user_settings.group_monitoring_enabled IS 'Permite monitoramento de grupos (opt-in)';
COMMENT ON COLUMN shadow_user_settings.always_ask_incomplete IS 'Sempre perguntar quando informações estão incompletas';
COMMENT ON COLUMN shadow_user_settings.gcal_check_conflicts IS 'Verificar conflitos no Google Calendar antes de criar compromissos';
