-- Migration: cron_jobs e sessions para SQLite local
-- Compatível com SQLiteStorage

-- Tabela de jobs agendados
CREATE TABLE IF NOT EXISTS cron_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,

    -- Agendamento
    schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('at', 'every', 'cron')),
    schedule_at_ms INTEGER,
    schedule_every_ms INTEGER,
    schedule_anchor_ms INTEGER,
    schedule_expr TEXT,
    schedule_tz TEXT DEFAULT 'America/Sao_Paulo',

    -- Ação
    action TEXT NOT NULL,
    params TEXT DEFAULT '{}',  -- JSON string

    -- Controle
    enabled INTEGER DEFAULT 1,
    delete_after_run INTEGER DEFAULT 0,

    -- Estado
    state_next_run_at_ms INTEGER,
    state_running_at_ms INTEGER,
    state_last_run_at_ms INTEGER,
    state_last_status TEXT CHECK (state_last_status IN ('ok', 'error', 'skipped')),
    state_last_error TEXT,
    state_last_duration_ms INTEGER,

    -- Timestamps
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cron_jobs_enabled ON cron_jobs(enabled);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_next_run ON cron_jobs(state_next_run_at_ms);
CREATE INDEX IF NOT EXISTS idx_cron_jobs_action ON cron_jobs(action);


-- Tabela de sessões
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL UNIQUE,
    participant_phone TEXT,
    kind TEXT NOT NULL DEFAULT 'direct' CHECK (kind IN ('direct', 'group')),

    -- Estado
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'idle', 'closed')),

    -- Contexto
    context_window TEXT DEFAULT '[]',  -- JSON array
    context_summary TEXT,

    -- Configurações
    defaults TEXT DEFAULT '{}',  -- JSON object

    -- Metadados
    metadata TEXT DEFAULT '{}',  -- JSON object
    label TEXT,
    display_name TEXT,

    -- Métricas
    message_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,

    -- Timestamps
    created_at TEXT,
    updated_at TEXT,
    last_activity_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_chat ON sessions(chat_id);
CREATE INDEX IF NOT EXISTS idx_sessions_participant ON sessions(participant_phone);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(last_activity_at);
