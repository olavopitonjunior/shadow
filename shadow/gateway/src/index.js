import http from "node:http";
import path from "node:path";
import { config, normalizeE164 } from "./config.js";
import { callAgent } from "./agent-client.js";
import { createSocket, setMessageHandler, getCurrentSocket, setConnectionHandler } from "./wa-session.js";
import { extractText, extractMediaInfo, isGroupJid, matchTrigger, toWhatsappJid, resolveJidToE164, normalizeLid, jidToE164, populateCacheFromContacts, isLidJid } from "./normalize.js";
import { LidCache } from "./lid-cache.js";

const outboundIds = new Set();
const rememberOutboundId = (id) => {
  if (!id) return;
  outboundIds.add(id);
  setTimeout(() => outboundIds.delete(id), 5 * 60 * 1000).unref?.();
};

// LID Cache for persistent LID -> E.164 mappings
const lidCache = new LidCache({
  persistPath: path.join(config.authDir, "lid-cache.json"),
  ttlMs: config.lidCacheTtlMs,
  maxSize: config.lidCacheMaxSize,
});

const isOwner = (senderE164) => {
  if (!senderE164 || !config.ownerE164) return false;
  return normalizeE164(senderE164) === config.ownerE164;
};

/**
 * Check if sender is allowed based on access mode
 * @param {Object} params
 * @param {string} params.senderE164 - Sender phone in E.164 format
 * @param {string} params.senderJid - Sender JID
 * @param {string} params.ownerLid - Owner's LID
 * @param {boolean} params.isFromMe - If message is from self
 * @param {string} params.chatJid - Chat JID (for group monitoring)
 * @param {string} params.chatType - "group" or "direct"
 * @returns {{ allowed: boolean, reason: string, monitorOnly: boolean }}
 */
const checkAccessAllowed = ({ senderE164, senderJid, ownerLid, isFromMe, chatJid, chatType }) => {
  // Open mode: everyone is allowed
  if (config.accessMode === "open") {
    return { allowed: true, reason: "open_mode", monitorOnly: false };
  }

  // Check if sender is owner (multiple detection strategies)
  const ownerByFromMe = Boolean(isFromMe);
  const ownerByPhone = senderE164 && isOwner(senderE164);
  const ownerByLid = ownerLid && senderJid && normalizeLid(senderJid) === normalizeLid(ownerLid);
  const isOwnerCheck = ownerByFromMe || ownerByPhone || ownerByLid;

  // Owner is always allowed (full access)
  if (isOwnerCheck) {
    return { allowed: true, reason: "owner", monitorOnly: false };
  }

  // Monitor ALL conversations mode (groups + direct messages)
  if (config.monitorAllGroups) {
    return { allowed: true, reason: "monitored_all", monitorOnly: true };
  }

  // Check if chat is a monitored group (for entity extraction)
  if (chatType === "group" && chatJid) {
    // Specific monitored groups
    if (config.monitoredGroups && config.monitoredGroups.includes(chatJid)) {
      return { allowed: true, reason: "monitored_group", monitorOnly: true };
    }
  }

  // Check if sender is a monitored contact (for direct messages)
  if (chatType === "direct" && senderJid) {
    // Normalize to compare with configured contacts
    const normalizedSender = senderE164 ? normalizeE164(senderE164) : null;
    if (normalizedSender && config.monitoredContacts && config.monitoredContacts.includes(normalizedSender)) {
      return { allowed: true, reason: "monitored_contact", monitorOnly: true };
    }
  }

  // Owner-only mode: only owner allowed
  if (config.accessMode === "owner_only") {
    return { allowed: false, reason: "not_owner", monitorOnly: false };
  }

  // Allowlist mode: check if sender is in allowlist
  if (config.accessMode === "allowlist") {
    const normalizedSender = senderE164 ? normalizeE164(senderE164) : null;
    const inAllowlist = normalizedSender && config.allowlist.includes(normalizedSender);
    if (inAllowlist) {
      return { allowed: true, reason: "allowlist", monitorOnly: false };
    }
    return { allowed: false, reason: "not_in_allowlist", monitorOnly: false };
  }

  // Default: deny (unknown access mode)
  return { allowed: false, reason: "unknown_mode", monitorOnly: false };
};

const shouldReplyTo = ({ actualIsOwner, chatType, triggered, isSelfChat }) => {
  // Se replyToOwnerOnly=false, responde a qualquer um
  if (!config.replyToOwnerOnly) {
    if (chatType === "group") return triggered || !config.groupTriggerRequired;
    if (config.dmTriggerRequired) return triggered;
    return true;
  }

  // Modo padrão: apenas owner (usando actualIsOwner já calculado com fallback de LID)
  if (!config.ownerE164) return false;
  if (!actualIsOwner) return false;
  if (chatType === "group") return !config.groupTriggerRequired || triggered;
  if (isSelfChat) return true;
  if (config.dmTriggerRequired) return triggered;
  return true;
};

const normalizePayload = ({ msg, text, chatType, senderE164, senderJid, remoteJid, pushName, isFromMe, ownerLid, resolvedVia, logger, mediaInfo }) => {
  const triggered = matchTrigger(text, config.triggerTokens);

  // Detecção de owner com múltiplas estratégias
  const ownerByFromMe = Boolean(isFromMe);
  const ownerByPhone = senderE164 && isOwner(senderE164);
  // Fallback: comparação direta de LID (quando resolução E.164 falha)
  const ownerByLid = ownerLid && senderJid && normalizeLid(senderJid) === normalizeLid(ownerLid);
  const actualIsOwner = ownerByFromMe || ownerByPhone || ownerByLid;

  // Log detalhado da resolução de owner
  if (logger) {
    logger.info({
      senderE164,
      senderJid,
      ownerLid,
      resolvedVia,
      ownerByFromMe,
      ownerByPhone,
      ownerByLid,
      actualIsOwner
    }, "Owner detection");
  }

  const selfChat = actualIsOwner && !isGroupJid(remoteJid);
  const shouldReply = shouldReplyTo({ actualIsOwner, chatType, triggered, isSelfChat: selfChat });

  return {
    message_id: msg.key?.id ?? null,
    chat_id: remoteJid,
    chat_type: chatType,
    sender_e164: senderE164,
    sender_jid: senderJid,
    sender_name: pushName ?? null,
    owner_e164: config.ownerE164,
    body: text,
    timestamp: msg.messageTimestamp ? Number(msg.messageTimestamp) * 1000 : Date.now(),
    is_owner: actualIsOwner,
    triggered,
    should_reply: shouldReply,
    // Campos de mídia (Phase 7A)
    media_type: mediaInfo?.type || null,
    media_url: mediaInfo?.url || null,
    media_mime_type: mediaInfo?.mimetype || null,
    metadata: {
      fromMe: Boolean(msg.key?.fromMe),
      remoteJid,
    },
  };
};

const startHttpServer = (logger) => {
  const server = http.createServer((req, res) => {
    // Rota: POST /send - enviar mensagem
    if (req.method === "POST" && req.url === "/send") {
      let body = "";
      req.on("data", (chunk) => {
        body += chunk.toString();
      });
      req.on("end", async () => {
        try {
          const sock = getCurrentSocket();
          if (!sock) {
            res.statusCode = 503;
            res.end("Not connected");
            return;
          }
          const payload = JSON.parse(body || "{}");
          const text = String(payload.text || "").trim();
          // Default to Shadow group for proactive messages, fallback to owner's phone
          const to = payload.to || config.shadowGroupJid || config.ownerE164;
          const jid = toWhatsappJid(to);
          if (!text || !jid) {
            res.statusCode = 400;
            res.end("Missing text/to");
            return;
          }
          const result = await sock.sendMessage(jid, { text });
          rememberOutboundId(result?.key?.id);
          res.statusCode = 200;
          res.end("ok");
        } catch (err) {
          logger.error({ err: String(err) }, "send endpoint failed");
          res.statusCode = 500;
          res.end("error");
        }
      });
      return;
    }

    // Rota: POST /create-shadow-group - criar grupo Shadow para onboarding
    if (req.method === "POST" && req.url === "/create-shadow-group") {
      req.on("data", () => {}); // Consumir body (não usado)
      req.on("end", async () => {
        try {
          const sock = getCurrentSocket();
          if (!sock) {
            res.statusCode = 503;
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify({ error: "Not connected" }));
            return;
          }

          // Criar grupo "Shadow" sem participantes adicionais (só o owner)
          logger.info("Creating Shadow group...");
          const group = await sock.groupCreate("Shadow", []);

          logger.info({ groupJid: group.id }, "Shadow group created");

          // Enviar mensagem de boas-vindas no grupo
          await sock.sendMessage(group.id, {
            text: `[Shadow] Ola! Sou seu assistente pessoal.

Minhas mensagens sempre comecam com [Shadow] para voce identificar.

Comandos:
- tarefa: descricao - criar tarefa
- lembrete: mensagem em data/hora - criar lembrete
- mostrar tarefas - listar pendencias
- ajuda - ver todos os comandos

Envie uma mensagem para comecar!`
          });

          res.statusCode = 200;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({
            success: true,
            groupJid: group.id,
            groupName: "Shadow"
          }));
        } catch (err) {
          logger.error({ err: String(err) }, "create-shadow-group failed");
          res.statusCode = 500;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: String(err) }));
        }
      });
      return;
    }

    // Rota: GET /status - status da conexão para setup CLI
    if (req.method === "GET" && req.url === "/status") {
      const sock = getCurrentSocket();
      const connected = Boolean(sock?.user?.id);
      res.statusCode = 200;
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({
        connected,
        phone: connected ? sock.user.id : null,
        lid: sock?.user?.lid || null,
        lidCacheStats: lidCache.getStats(),
      }));
      return;
    }

    // Rota: GET /groups - listar grupos (ajuda a descobrir JIDs para monitoramento)
    if (req.method === "GET" && req.url === "/groups") {
      (async () => {
        try {
          const sock = getCurrentSocket();
          if (!sock) {
            res.statusCode = 503;
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify({ error: "Not connected" }));
            return;
          }

          // Fetch groups from Baileys store
          const groups = await sock.groupFetchAllParticipating();
          const groupList = Object.entries(groups).map(([jid, meta]) => ({
            jid,
            name: meta.subject || "Unknown",
            participants: meta.participants?.length || 0,
            isMonitored: config.monitoredGroups?.includes(jid) || config.monitorAllGroups,
          }));

          res.statusCode = 200;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({
            groups: groupList,
            monitorAllGroups: config.monitorAllGroups,
            monitoredGroups: config.monitoredGroups,
          }));
        } catch (err) {
          logger.error({ err: String(err) }, "groups endpoint failed");
          res.statusCode = 500;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: String(err) }));
        }
      })();
      return;
    }

    // Rota não encontrada
    res.statusCode = 404;
    res.end("Not found");
  });

  server.listen(config.gatewayPort, () => {
    logger.info(`Gateway HTTP listening on :${config.gatewayPort}`);
  });
};

const main = async () => {
  // Load LID cache from disk
  await lidCache.load();

  const { logger } = await createSocket();
  lidCache.logger = logger; // Set logger for cache operations
  startHttpServer(logger);

  // Set up connection handler for LID cache event listeners
  setConnectionHandler((sock, log) => {
    // Listen for phoneNumberShare events (explicit LID→JID mappings)
    sock.ev.on("chats.phoneNumberShare", ({ lid, jid }) => {
      const e164 = jidToE164(jid);
      if (e164 && lid) {
        lidCache.set(lid, e164);
        log.info({ lid, e164 }, "LID cache: received mapping from phoneNumberShare");
      }
    });

    // Listen for contacts.upsert to batch populate cache
    sock.ev.on("contacts.upsert", (contacts) => {
      populateCacheFromContacts(contacts, lidCache);
      log.debug({ count: contacts.length }, "LID cache: processed contacts.upsert");
    });

    log.info("LID cache event listeners registered");
  });

  // Usar setMessageHandler para que o handler seja reattachado em reconexões
  const handleMessages = async (upsert) => {
    const sock = getCurrentSocket(); // Sempre pegar o socket atual
    logger.info({ type: upsert.type, count: upsert.messages?.length }, "messages.upsert received");

    if (upsert.type !== "notify" && upsert.type !== "append") return;
    for (const msg of upsert.messages ?? []) {
      if (!msg.message) {
        logger.info("Skipped: no message content");
        continue;
      }
      if (!msg.key?.remoteJid) {
        logger.info("Skipped: no remoteJid");
        continue;
      }
      if (msg.key.remoteJid.endsWith("@broadcast") || msg.key.remoteJid.endsWith("@status")) {
        logger.info("Skipped: broadcast/status");
        continue;
      }

      if (config.ignoreFromMe && msg.key.fromMe) {
        logger.info({ fromMe: msg.key.fromMe, ignoreFromMe: config.ignoreFromMe }, "Skipped: fromMe ignored");
        continue;
      }
      if (msg.key.id && outboundIds.has(msg.key.id)) {
        logger.info("Skipped: outbound message");
        continue;
      }

      // Filter Shadow's own messages by prefix (failsafe for welcome/system messages)
      const rawText = extractText(msg.message);
      const shadowPrefix = config.selfChatPrefix || "[Shadow]";
      if (rawText && rawText.toLowerCase().startsWith(shadowPrefix.toLowerCase())) {
        logger.info({ text: rawText.substring(0, 40) }, "Skipped: Shadow prefix message");
        continue;
      }

      const remoteJid = msg.key.remoteJid;
      const chatType = isGroupJid(remoteJid) ? "group" : "direct";

      // Se mensagem é fromMe, usar sock.user.id como senderJid (JID real do owner)
      let senderJid;
      if (msg.key.fromMe && sock.user?.id) {
        // sock.user.id tem formato "5511947174266:7@s.whatsapp.net"
        senderJid = sock.user.id;
        logger.info({ fromMe: true, senderJid, sockUserId: sock.user.id }, "[LID] Using sock.user.id for fromMe");
      } else if (chatType === "group") {
        senderJid = msg.key.participant;
      } else {
        senderJid = remoteJid;
      }

      // Resolver LID → E.164 usando múltiplas estratégias (cache, Baileys)
      const lidMapping = sock.signalRepository?.lidMapping;
      const { e164: senderE164, lid: senderLid, resolvedVia, cacheHit } = await resolveJidToE164(senderJid, lidMapping, lidCache);

      // Log LID resolution details for debugging
      if (isLidJid(senderJid) && !senderE164) {
        logger.warn({
          senderJid,
          normalizedLid: senderLid,
          ownerLid: sock.user?.lid,
          resolvedVia,
          cacheStats: lidCache.getStats(),
          hasLidMapping: !!lidMapping?.getPNForLID,
        }, "LID resolution failed - sender E.164 unknown");
      } else if (cacheHit) {
        logger.debug({ senderJid, senderE164, resolvedVia }, "LID resolved from cache");
      }

      const text = extractText(msg.message).trim();
      const mediaInfo = extractMediaInfo(msg.message);

      // Só pula se não tem texto NEM mídia
      if (!text && !mediaInfo) continue;

      const ownerLid = sock.user?.lid;

      // Access mode gating - check if sender is allowed
      const accessCheck = checkAccessAllowed({
        senderE164,
        senderJid,
        ownerLid,
        isFromMe: msg.key.fromMe,
        chatJid: remoteJid,
        chatType,
      });

      if (!accessCheck.allowed) {
        logger.info({
          senderE164,
          senderJid,
          ownerLid,
          resolvedVia,
          cacheHit,
          accessMode: config.accessMode,
          reason: accessCheck.reason,
          lidCacheSize: lidCache.getStats().size,
        }, "Access denied, ignoring message");
        continue;
      }

      logger.debug({ accessMode: config.accessMode, reason: accessCheck.reason, monitorOnly: accessCheck.monitorOnly }, "Access granted");

      const payload = normalizePayload({ msg, text, chatType, senderE164, senderJid, remoteJid, pushName: msg.pushName, isFromMe: msg.key.fromMe, ownerLid, resolvedVia, logger, mediaInfo });

      // For monitored groups, force should_reply=false (entity extraction only)
      if (accessCheck.monitorOnly) {
        payload.should_reply = false;
        payload.monitor_only = true;
        logger.info({ chatJid: remoteJid, reason: accessCheck.reason }, "Monitor-only mode: capturing for entity extraction");
      }

      logger.info({
        text: text.substring(0, 50),
        mediaType: mediaInfo?.type || null,
        senderE164,
        senderJid,
        pushName: msg.pushName || null,
        ownerLid,
        chatType,
        is_owner: payload.is_owner,
        should_reply: payload.should_reply,
        agentUrl: config.agentUrl
      }, "Calling agent");

      const agentResult = await callAgent(config.agentUrl, payload, logger, config.agentToken);

      logger.info({
        reply: agentResult?.reply?.substring(0, 50),
        error: agentResult?.error,
        should_reply: payload.should_reply
      }, "Agent response");

      if (payload.should_reply && agentResult?.reply) {
        // Adicionar prefixo [Shadow] em TODAS as respostas para identificacao
        let replyText = agentResult.reply;

        if (config.selfChatPrefix) {
          replyText = `${config.selfChatPrefix} ${replyText}`;
        }

        const isSelfChat = msg.key.fromMe && !isGroupJid(remoteJid);

        // Redirecionar self-chat para Shadow Group (evita problema do relógio)
        // Note: mensagens monitoradas (monitor_only=true) não chegam aqui porque
        // should_reply=false. O Python envia confirmações via /send endpoint.
        let replyJid = remoteJid;
        if (isSelfChat && config.shadowGroupJid) {
          replyJid = config.shadowGroupJid;
          logger.info({ from: remoteJid, to: replyJid }, "Redirecting self-chat to Shadow group");
        }

        logger.info({ to: replyJid, isSelfChat }, "Sending reply");
        const result = await sock.sendMessage(replyJid, { text: replyText });
        const messageId = result?.key?.id;
        rememberOutboundId(messageId);
        logger.info({ messageId }, "Reply sent");
      } else {
        logger.info({ should_reply: payload.should_reply, hasReply: !!agentResult?.reply }, "Not sending reply");
      }
    }
  };

  // Registrar o handler - será reattachado automaticamente em reconexões
  setMessageHandler(handleMessages);

  logger.info("Shadow gateway iniciado.");
};

main().catch((err) => {
  console.error("Gateway failed:", err);
  process.exit(1);
});