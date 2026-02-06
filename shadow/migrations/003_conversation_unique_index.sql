-- Ensure unique per-user conversation mapping
CREATE UNIQUE INDEX IF NOT EXISTS shadow_conversations_user_chat_id_idx
  ON shadow_conversations (user_id, chat_id);