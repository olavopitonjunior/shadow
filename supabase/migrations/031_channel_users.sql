-- Migration 031: Channel Users, Messages, and Templates
-- Tables for the official WhatsApp channel (Evolution API / Meta Cloud API).
-- Supports multi-user SaaS with per-phone accounts.

-- Channel users: one row per phone number that interacts with Shadow
CREATE TABLE IF NOT EXISTS shadow_channel_users (
    id TEXT PRIMARY KEY,
    phone_e164 TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL,
    instance_id TEXT,
    display_name TEXT,
    user_type TEXT DEFAULT 'standalone',
    channel TEXT DEFAULT 'evolution',
    status TEXT DEFAULT 'active',
    last_message_at TEXT,
    last_window_opened_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_channel_users_phone ON shadow_channel_users(phone_e164);
CREATE INDEX IF NOT EXISTS idx_channel_users_owner ON shadow_channel_users(owner_id);

-- Channel messages: log of all inbound/outbound messages via channel
CREATE TABLE IF NOT EXISTS shadow_channel_messages (
    id TEXT PRIMARY KEY,
    external_id TEXT UNIQUE,
    user_phone TEXT NOT NULL,
    direction TEXT NOT NULL,
    channel TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',
    content TEXT,
    template_name TEXT,
    status TEXT DEFAULT 'sent',
    cost_category TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_channel_msgs_ext ON shadow_channel_messages(external_id);
CREATE INDEX IF NOT EXISTS idx_channel_msgs_phone ON shadow_channel_messages(user_phone);

-- Channel templates: pre-approved message templates (for Meta Cloud API)
CREATE TABLE IF NOT EXISTS shadow_channel_templates (
    id TEXT PRIMARY KEY,
    template_name TEXT NOT NULL UNIQUE,
    language TEXT DEFAULT 'pt_BR',
    category TEXT,
    status TEXT DEFAULT 'draft',
    body_text TEXT,
    components TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
