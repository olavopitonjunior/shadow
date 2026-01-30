-- Migration: shadow_sessions
-- Tabela para gerenciamento de sessões de conversa

CREATE TABLE IF NOT EXISTS shadow_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES shadow_users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES shadow_organizations(id) ON DELETE CASCADE,

    -- Identificação da sessão
    chat_id TEXT NOT NULL,                    -- JID do WhatsApp ou identificador único
    participant_phone TEXT,                    -- Telefone do participante (E.164)
    kind TEXT NOT NULL DEFAULT 'direct' CHECK (kind IN ('direct', 'group')),

    -- Estado da sessão
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'idle', 'closed')),

    -- Contexto
    context_window JSONB DEFAULT '[]',         -- Últimas N mensagens para contexto
    context_summary TEXT,                      -- Resumo do contexto (para sessões longas)

    -- Configurações por sessão
    defaults JSONB DEFAULT '{}',               -- Config específica (model, temp, etc.)

    -- Metadados
    metadata JSONB DEFAULT '{}',               -- Dados adicionais
    label TEXT,                                -- Rótulo opcional
    display_name TEXT,                         -- Nome de exibição

    -- Métricas
    message_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unicidade por usuário + chat
    UNIQUE(user_id, chat_id)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_user ON shadow_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_chat ON shadow_sessions(chat_id);
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_participant ON shadow_sessions(participant_phone);
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_status ON shadow_sessions(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_shadow_sessions_activity ON shadow_sessions(last_activity_at DESC);

-- Trigger para atualizar updated_at
CREATE OR REPLACE FUNCTION update_shadow_sessions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_shadow_sessions_updated_at ON shadow_sessions;
CREATE TRIGGER trigger_shadow_sessions_updated_at
    BEFORE UPDATE ON shadow_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_shadow_sessions_updated_at();

-- Comentários
COMMENT ON TABLE shadow_sessions IS 'Sessões de conversa com contexto persistente';
COMMENT ON COLUMN shadow_sessions.context_window IS 'Array JSON com últimas mensagens para contexto do agente';
COMMENT ON COLUMN shadow_sessions.defaults IS 'Configurações específicas da sessão (model override, etc.)';
