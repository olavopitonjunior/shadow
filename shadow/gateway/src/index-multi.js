/**
 * Shadow Gateway - Multi-User Mode
 *
 * This entry point supports multiple WhatsApp connections.
 * Use this for SaaS deployments where each user has their own connection.
 *
 * Usage:
 *   node src/index-multi.js
 *
 * Endpoints:
 *   POST /sessions/:userId/connect  - Start connection, get QR
 *   GET  /sessions/:userId/qr       - Get current QR code
 *   GET  /sessions/:userId/status   - Get connection status
 *   POST /sessions/:userId/send     - Send message
 *   DELETE /sessions/:userId        - Disconnect session
 *   GET  /sessions                  - List all sessions
 *   POST /send                      - Legacy single-user (uses default session)
 *   GET  /status                    - Legacy single-user status
 */

import http from "node:http";
import { config, normalizeE164 } from "./config.js";
import { callAgent } from "./agent-client.js";
import { GatewayManager, SESSION_STATUS } from "./manager.js";
import { extractText, extractMediaInfo, isGroupJid, matchTrigger, toWhatsappJid, resolveJidToE164, normalizeLid, isLidJid } from "./normalize.js";
import pino from "pino";

const logger = pino({ level: config.logLevel });
const manager = new GatewayManager({
  baseAuthDir: config.authDir || "./auth_sessions",
  logLevel: config.logLevel,
});

const DEFAULT_USER = "default";

// Track outbound messages to avoid echo
const outboundIds = new Map(); // userId -> Set<messageId>
const rememberOutboundId = (userId, id) => {
  if (!id) return;
  if (!outboundIds.has(userId)) {
    outboundIds.set(userId, new Set());
  }
  const set = outboundIds.get(userId);
  set.add(id);
  setTimeout(() => set.delete(id), 5 * 60 * 1000).unref?.();
};

const isOwner = (senderE164, ownerE164) => {
  if (!senderE164 || !ownerE164) return false;
  return normalizeE164(senderE164) === normalizeE164(ownerE164);
};

/**
 * Message handler for all sessions
 * @param {string} userId - User ID
 * @param {object} upsert - Message upsert from Baileys
 * @param {object} sock - Baileys socket
 * @param {object} lidCache - LidCache instance for this session
 */
const handleMessage = async (userId, upsert, sock, lidCache = null) => {
  if (upsert.type !== "notify" && upsert.type !== "append") return;

  const userOutbound = outboundIds.get(userId) || new Set();

  for (const msg of upsert.messages ?? []) {
    if (!msg.message || !msg.key?.remoteJid) continue;
    if (msg.key.remoteJid.endsWith("@broadcast") || msg.key.remoteJid.endsWith("@status")) continue;

    if (config.ignoreFromMe && msg.key.fromMe) continue;
    if (msg.key.id && userOutbound.has(msg.key.id)) continue;

    const remoteJid = msg.key.remoteJid;
    const chatType = isGroupJid(remoteJid) ? "group" : "direct";

    // Determine sender
    let senderJid;
    if (msg.key.fromMe && sock.user?.id) {
      senderJid = sock.user.id;
    } else if (chatType === "group") {
      senderJid = msg.key.participant;
    } else {
      senderJid = remoteJid;
    }

    // Resolve to E.164 using multi-tier resolution (cache, Baileys)
    const lidMapping = sock.signalRepository?.lidMapping;
    const { e164: senderE164, lid: senderLid, resolvedVia, cacheHit } = await resolveJidToE164(senderJid, lidMapping, lidCache);

    // Log LID resolution details for debugging
    if (isLidJid(senderJid) && !senderE164) {
      logger.warn({
        userId,
        senderJid,
        normalizedLid: senderLid,
        ownerLid: sock.user?.lid,
        resolvedVia,
        cacheStats: lidCache?.getStats(),
        hasLidMapping: !!lidMapping?.getPNForLID,
      }, "LID resolution failed - sender E.164 unknown");
    }

    const text = extractText(msg.message).trim();
    const mediaInfo = extractMediaInfo(msg.message);
    if (!text && !mediaInfo) continue;

    const ownerLid = sock.user?.lid;
    const triggered = matchTrigger(text, config.triggerTokens);

    // Owner detection
    const ownerByFromMe = Boolean(msg.key.fromMe);
    const ownerByPhone = senderE164 && isOwner(senderE164, config.ownerE164);
    const ownerByLid = ownerLid && senderJid && normalizeLid(senderJid) === normalizeLid(ownerLid);
    const actualIsOwner = ownerByFromMe || ownerByPhone || ownerByLid;

    // Determine if we should reply
    const selfChat = actualIsOwner && !isGroupJid(remoteJid);
    let shouldReply = false;
    if (!config.replyToOwnerOnly) {
      if (chatType === "group") {
        shouldReply = triggered || !config.groupTriggerRequired;
      } else {
        shouldReply = !config.dmTriggerRequired || triggered;
      }
    } else if (actualIsOwner) {
      if (chatType === "group") {
        shouldReply = !config.groupTriggerRequired || triggered;
      } else if (selfChat || !config.dmTriggerRequired) {
        shouldReply = true;
      } else {
        shouldReply = triggered;
      }
    }

    // Build payload for agent
    const payload = {
      user_id: userId, // Multi-user: include userId
      message_id: msg.key?.id ?? null,
      chat_id: remoteJid,
      chat_type: chatType,
      sender_e164: senderE164,
      sender_jid: senderJid,
      sender_name: msg.pushName ?? null,
      owner_e164: config.ownerE164,
      body: text,
      timestamp: msg.messageTimestamp ? Number(msg.messageTimestamp) * 1000 : Date.now(),
      is_owner: actualIsOwner,
      triggered,
      should_reply: shouldReply,
      media_type: mediaInfo?.type || null,
      media_url: mediaInfo?.url || null,
      media_mime_type: mediaInfo?.mimetype || null,
      metadata: {
        fromMe: Boolean(msg.key?.fromMe),
        remoteJid,
      },
    };

    logger.info({
      userId,
      text: text.substring(0, 50),
      senderE164,
      should_reply: shouldReply,
    }, "Processing message");

    const agentResult = await callAgent(config.agentUrl, payload, logger, config.agentToken);

    if (shouldReply && agentResult?.reply) {
      let replyText = agentResult.reply;
      if (config.selfChatPrefix) {
        replyText = `${config.selfChatPrefix} ${replyText}`;
      }

      const result = await sock.sendMessage(remoteJid, { text: replyText });
      rememberOutboundId(userId, result?.key?.id);
      logger.info({ userId, messageId: result?.key?.id }, "Reply sent");
    }
  }
};

// Set up message handler
manager.setMessageHandler(handleMessage);

/**
 * Parse JSON body from request
 */
const parseBody = (req) => {
  return new Promise((resolve) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk.toString();
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(body || "{}"));
      } catch {
        resolve({});
      }
    });
  });
};

/**
 * Send JSON response
 */
const jsonResponse = (res, data, status = 200) => {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(data));
};

/**
 * HTTP Server
 */
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const path = url.pathname;

  // Multi-user endpoints
  const sessionMatch = path.match(/^\/sessions\/([^/]+)(\/(.+))?$/);

  if (sessionMatch) {
    const userId = decodeURIComponent(sessionMatch[1]);
    const action = sessionMatch[3] || "";

    // POST /sessions/:userId/connect
    if (req.method === "POST" && action === "connect") {
      const result = await manager.connect(userId);
      jsonResponse(res, result);
      return;
    }

    // GET /sessions/:userId/qr
    if (req.method === "GET" && action === "qr") {
      const result = manager.getQR(userId);
      jsonResponse(res, result);
      return;
    }

    // GET /sessions/:userId/status
    if (req.method === "GET" && action === "status") {
      const result = manager.getStatus(userId);
      jsonResponse(res, result);
      return;
    }

    // POST /sessions/:userId/send
    if (req.method === "POST" && action === "send") {
      const body = await parseBody(req);
      const result = await manager.send(userId, body.to, body.text);
      jsonResponse(res, result, result.success ? 200 : 400);
      return;
    }

    // GET /sessions/:userId/groups
    if (req.method === "GET" && action === "groups") {
      const session = manager.sessions.get(userId);
      if (!session || session.status !== SESSION_STATUS.CONNECTED) {
        jsonResponse(res, { groups: [], error: "Not connected" });
        return;
      }
      try {
        const participating = await session.sock.groupFetchAllParticipating();
        const groups = Object.values(participating).map((g) => ({
          id: g.id,
          subject: g.subject,
          size: g.size || g.participants?.length || 0,
          creation: g.creation,
          owner: g.owner,
        }));
        jsonResponse(res, { groups });
      } catch (err) {
        jsonResponse(res, { groups: [], error: String(err) });
      }
      return;
    }

    // DELETE /sessions/:userId
    if (req.method === "DELETE" && !action) {
      const result = await manager.disconnect(userId);
      jsonResponse(res, result, result.success ? 200 : 404);
      return;
    }
  }

  // GET /sessions - List all sessions
  if (req.method === "GET" && path === "/sessions") {
    const sessions = manager.listSessions();
    jsonResponse(res, { sessions });
    return;
  }

  // Legacy single-user endpoints (use default session)

  // POST /send
  if (req.method === "POST" && path === "/send") {
    const body = await parseBody(req);
    const status = manager.getStatus(DEFAULT_USER);

    // Auto-connect if not connected
    if (status.status !== SESSION_STATUS.CONNECTED) {
      await manager.connect(DEFAULT_USER);
    }

    const result = await manager.send(DEFAULT_USER, body.to || config.ownerE164, body.text);
    if (result.success) {
      res.statusCode = 200;
      res.end("ok");
    } else {
      res.statusCode = 400;
      res.end(result.error);
    }
    return;
  }

  // GET /status
  if (req.method === "GET" && path === "/status") {
    const status = manager.getStatus(DEFAULT_USER);
    jsonResponse(res, {
      connected: status.status === SESSION_STATUS.CONNECTED,
      phone: status.phone,
      lid: status.lid,
      lidCacheStats: status.lidCacheStats,
    });
    return;
  }

  // 404
  res.statusCode = 404;
  res.end("Not found");
});

// Start server and auto-connect default session
const main = async () => {
  server.listen(config.gatewayPort, () => {
    logger.info(`Multi-user gateway listening on :${config.gatewayPort}`);
  });

  // Auto-connect default session for backward compatibility
  logger.info("Auto-connecting default session...");
  await manager.connect(DEFAULT_USER);

  logger.info("Shadow multi-user gateway started");
};

main().catch((err) => {
  console.error("Gateway failed:", err);
  process.exit(1);
});
