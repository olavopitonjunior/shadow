import dotenv from "dotenv";
import path from "node:path";

dotenv.config();

const parseList = (value, fallback = []) => {
  if (!value) return fallback;
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
};

const normalizeE164 = (value) => {
  if (!value) return null;
  const stripped = String(value).replace(/^whatsapp:/i, "").trim();
  const digits = stripped.replace(/[^\d+]/g, "");
  if (!digits) return null;
  return digits.startsWith("+") ? `+${digits.slice(1)}` : `+${digits}`;
};

const envOwner = normalizeE164(process.env.SHADOW_OWNER_E164 || "");

const config = {
  ownerE164: envOwner,
  // Unified allowlist variable (replaces SHADOW_ALLOW_FROM)
  allowlist: parseList(process.env.SHADOW_ALLOWLIST).map(normalizeE164).filter(Boolean),
  agentUrl: process.env.SHADOW_AGENT_URL || "http://127.0.0.1:8090/process",
  agentToken: process.env.SHADOW_AGENT_TOKEN || "",
  authDir: process.env.SHADOW_AUTH_DIR || path.join(process.cwd(), "auth_info"),
  logLevel: process.env.SHADOW_LOG_LEVEL || "info",
  triggerTokens: parseList(process.env.SHADOW_TRIGGER_TOKENS, ["@shadow", "/shadow", "shadow:"]),
  groupTriggerRequired: process.env.SHADOW_GROUP_TRIGGER_REQUIRED !== "false",
  dmTriggerRequired: process.env.SHADOW_DM_TRIGGER_REQUIRED === "true",
  ignoreFromMe: process.env.SHADOW_IGNORE_FROM_ME !== "false",
  replyToOwnerOnly: process.env.SHADOW_REPLY_OWNER_ONLY !== "false",
  gatewayPort: Number.parseInt(process.env.SHADOW_GATEWAY_PORT || "18790", 10),
  // Prefixo para identificar respostas do Shadow em self-chat (como Moltbot faz)
  selfChatPrefix: process.env.SHADOW_SELF_CHAT_PREFIX || "[Shadow]",
  // Modo de acesso: "owner_only" | "allowlist" | "open"
  accessMode: process.env.SHADOW_ACCESS_MODE || "owner_only",
  // Shadow Group JID para redirecionar self-chat (evita problema do relógio)
  shadowGroupJid: process.env.SHADOW_GROUP_JID || null,
  // LID cache settings
  lidCacheTtlMs: Number.parseInt(process.env.SHADOW_LID_CACHE_TTL_MS || "86400000", 10), // 24 hours
  lidCacheMaxSize: Number.parseInt(process.env.SHADOW_LID_CACHE_MAX_SIZE || "10000", 10),
};

if (!config.ownerE164) {
  console.warn("[gateway] SHADOW_OWNER_E164 not set. Replies will be disabled.");
}

export { config, normalizeE164 };