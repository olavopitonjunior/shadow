import { normalizeE164 } from "./config.js";

export const isGroupJid = (jid) => typeof jid === "string" && jid.endsWith("@g.us");

export const jidToE164 = (jid) => {
  if (!jid || typeof jid !== "string") return null;
  if (isGroupJid(jid)) return null;

  // NÃO aceitar LIDs - eles precisam ser resolvidos via lidMapping
  if (/@lid$/i.test(jid)) return null;

  // Formato: "5511947174266:7@s.whatsapp.net"
  const match = jid.match(/^(\d+)(?::\d+)?@s\.whatsapp\.net$/i);
  if (!match) return null;

  return normalizeE164(match[1]);
};

export const toWhatsappJid = (number) => {
  if (!number) return null;
  const stripped = String(number).replace(/^whatsapp:/i, "").trim();
  if (stripped.includes("@")) return stripped;
  const normalized = normalizeE164(stripped);
  if (!normalized) return null;
  const digits = normalized.replace(/\D/g, "");
  return `${digits}@s.whatsapp.net`;
};

export const extractText = (message) => {
  if (!message) return "";
  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    message.videoMessage?.caption ||
    message.documentMessage?.caption ||
    ""
  );
};

/**
 * Extrai informações de mídia (áudio, imagem, vídeo, documento).
 * @param {object} message - O objeto de mensagem do Baileys
 * @returns {object|null} - Informações da mídia ou null se não houver
 */
export const extractMediaInfo = (message) => {
  if (!message) return null;

  if (message.audioMessage) {
    return {
      type: "audio",
      url: message.audioMessage.url,
      mimetype: message.audioMessage.mimetype || "audio/ogg",
      ptt: message.audioMessage.ptt || false,
      seconds: message.audioMessage.seconds || null,
    };
  }

  if (message.imageMessage) {
    return {
      type: "image",
      url: message.imageMessage.url,
      mimetype: message.imageMessage.mimetype || "image/jpeg",
      caption: message.imageMessage.caption || null,
    };
  }

  if (message.videoMessage) {
    return {
      type: "video",
      url: message.videoMessage.url,
      mimetype: message.videoMessage.mimetype || "video/mp4",
      caption: message.videoMessage.caption || null,
      seconds: message.videoMessage.seconds || null,
    };
  }

  if (message.documentMessage) {
    return {
      type: "document",
      url: message.documentMessage.url,
      mimetype: message.documentMessage.mimetype,
      filename: message.documentMessage.fileName || null,
      caption: message.documentMessage.caption || null,
    };
  }

  return null;
};

export const matchTrigger = (text, tokens) => {
  if (!text) return false;
  const lowered = text.toLowerCase();
  return tokens.some((token) => lowered.includes(token.toLowerCase()));
};

/**
 * Verifica se um JID é um LID (Linked ID).
 */
export const isLidJid = (jid) => {
  return typeof jid === "string" && /@lid$/i.test(jid);
};

/**
 * Normaliza um LID removendo sufixo de dispositivo e lowercase.
 * "45119336108132:5@lid" -> "45119336108132@lid"
 */
export const normalizeLid = (jid) => {
  if (!jid || typeof jid !== "string") return null;
  const match = jid.match(/^(\d+)(?::\d+)?@lid$/i);
  if (!match) return null;
  return `${match[1]}@lid`.toLowerCase();
};

/**
 * Resolve um JID para E.164 usando múltiplas estratégias:
 * Tier 1: Extração direta (JIDs normais)
 * Tier 2: Cache lookup (LidCache)
 * Tier 3: Baileys lidMapping.getPNForLID()
 *
 * @param {string} jid - O JID a resolver
 * @param {object} lidMapping - sock.signalRepository?.lidMapping
 * @param {object} lidCache - LidCache instance (optional)
 * @returns {Promise<{e164: string|null, lid: string|null, resolvedVia: string, cacheHit: boolean}>}
 */
export const resolveJidToE164 = async (jid, lidMapping = null, lidCache = null) => {
  // Tier 1: Extração direta (funciona para JIDs normais)
  const direct = jidToE164(jid);
  if (direct) {
    return { e164: direct, lid: null, resolvedVia: "direct", cacheHit: false };
  }

  // Se não é LID, não conseguimos resolver
  if (!isLidJid(jid)) {
    return { e164: null, lid: null, resolvedVia: "failed", cacheHit: false };
  }

  const normalizedLid = normalizeLid(jid);

  // Tier 2: Cache lookup
  if (lidCache) {
    const cached = lidCache.getE164(jid);
    if (cached) {
      return { e164: cached, lid: normalizedLid, resolvedVia: "cache", cacheHit: true };
    }
  }

  // Tier 3: Baileys lidMapping
  if (lidMapping?.getPNForLID) {
    try {
      const pnJid = await lidMapping.getPNForLID(jid);
      if (pnJid) {
        const resolved = jidToE164(pnJid);
        if (resolved) {
          // Store in cache for future lookups
          if (lidCache) {
            lidCache.set(jid, resolved);
          }
          return { e164: resolved, lid: normalizedLid, resolvedVia: "baileys_lid", cacheHit: false };
        }
      }
    } catch (err) {
      // Fallback silencioso
    }
  }

  return { e164: null, lid: normalizedLid, resolvedVia: "failed", cacheHit: false };
};

/**
 * Populate cache from contacts array (from contacts.upsert event).
 * @param {Array} contacts - Array of contact objects from Baileys
 * @param {object} lidCache - LidCache instance
 */
export const populateCacheFromContacts = (contacts, lidCache) => {
  if (!lidCache || !Array.isArray(contacts)) return;

  for (const contact of contacts) {
    // contact.id is the standard JID, contact.lid is the LID
    if (contact.id && contact.lid) {
      const e164 = jidToE164(contact.id);
      if (e164) {
        lidCache.set(contact.lid, e164);
      }
    }
  }
};