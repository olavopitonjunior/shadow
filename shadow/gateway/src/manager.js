/**
 * Gateway Manager - Multi-user Baileys session management
 *
 * This module manages multiple WhatsApp connections, one per user.
 * Each user gets their own auth folder and Baileys socket.
 *
 * Usage:
 *   import { GatewayManager } from "./manager.js";
 *   const manager = new GatewayManager();
 *   await manager.connect("user_123");
 *   await manager.send("user_123", "+5511999999999", "Hello!");
 */

import {
  default as makeWASocket,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import pino from "pino";
import path from "node:path";
import fs from "node:fs";
import { toWhatsappJid, jidToE164, populateCacheFromContacts } from "./normalize.js";
import { LidCache } from "./lid-cache.js";
import { config } from "./config.js";

const SESSION_STATUS = {
  DISCONNECTED: "disconnected",
  CONNECTING: "connecting",
  CONNECTED: "connected",
  QR_PENDING: "qr_pending",
  LOGGED_OUT: "logged_out",
};

/**
 * Gateway Manager for multi-user WhatsApp connections
 */
class GatewayManager {
  constructor(options = {}) {
    this.sessions = new Map(); // userId -> { sock, status, authPath, qr, logger }
    this.baseAuthDir = options.baseAuthDir || "./auth_sessions";
    this.logLevel = options.logLevel || "info";
    this.messageHandler = options.messageHandler || null;

    // Ensure base auth directory exists
    if (!fs.existsSync(this.baseAuthDir)) {
      fs.mkdirSync(this.baseAuthDir, { recursive: true });
    }
  }

  /**
   * Get auth path for a user
   * @param {string} userId
   * @returns {string}
   */
  getAuthPath(userId) {
    // Sanitize userId to prevent path traversal
    const safeUserId = userId.replace(/[^a-zA-Z0-9_-]/g, "_");
    return path.join(this.baseAuthDir, safeUserId);
  }

  /**
   * Connect a user session
   * @param {string} userId
   * @returns {Promise<{ success: boolean, status: string, qr?: string }>}
   */
  async connect(userId) {
    // If already connected, return status
    const existing = this.sessions.get(userId);
    if (existing && existing.status === SESSION_STATUS.CONNECTED) {
      return { success: true, status: SESSION_STATUS.CONNECTED };
    }

    const authPath = this.getAuthPath(userId);
    const logger = pino({ level: this.logLevel });

    logger.info({ userId, authPath }, "Starting connection");

    const { state, saveCreds } = await useMultiFileAuthState(authPath);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
      version,
      logger,
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      printQRInTerminal: false,
      markOnlineOnConnect: false,
      syncFullHistory: false,
      browser: ["shadow", "gateway-multi", "1.0.0"],
    });

    // Create LID cache for this session
    const lidCache = new LidCache({
      persistPath: path.join(authPath, "lid-cache.json"),
      ttlMs: config.lidCacheTtlMs,
      maxSize: config.lidCacheMaxSize,
      logger,
    });
    await lidCache.load();

    // Create session entry
    const session = {
      sock,
      status: SESSION_STATUS.CONNECTING,
      authPath,
      qr: null,
      logger,
      userId,
      lidCache,
    };
    this.sessions.set(userId, session);

    // Set up event handlers
    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        session.status = SESSION_STATUS.QR_PENDING;
        session.qr = qr;
        logger.info({ userId }, "QR code received");
        qrcode.generate(qr, { small: true });
      }

      if (connection === "close") {
        const status = lastDisconnect?.error?.output?.statusCode;
        if (status === DisconnectReason.loggedOut) {
          logger.error({ userId }, "Logged out - need to re-scan QR");
          session.status = SESSION_STATUS.LOGGED_OUT;
          session.qr = null;
        } else {
          logger.warn({ userId }, "Connection closed, reconnecting...");
          session.status = SESSION_STATUS.CONNECTING;
          // Auto-reconnect
          this.connect(userId).catch((err) =>
            logger.error({ userId, err: String(err) }, "Reconnect failed")
          );
        }
      }

      if (connection === "open") {
        logger.info({ userId }, "Connected");
        session.status = SESSION_STATUS.CONNECTED;
        session.qr = null;

        // Set up LID cache event listeners
        sock.ev.on("chats.phoneNumberShare", ({ lid, jid }) => {
          const e164 = jidToE164(jid);
          if (e164 && lid) {
            session.lidCache.set(lid, e164);
            logger.info({ userId, lid, e164 }, "LID cache: received mapping from phoneNumberShare");
          }
        });

        sock.ev.on("contacts.upsert", (contacts) => {
          populateCacheFromContacts(contacts, session.lidCache);
          logger.debug({ userId, count: contacts.length }, "LID cache: processed contacts.upsert");
        });

        logger.info({ userId }, "LID cache event listeners registered");
      }
    });

    // Attach message handler if provided
    if (this.messageHandler) {
      sock.ev.on("messages.upsert", (upsert) => {
        this.messageHandler(userId, upsert, sock, session.lidCache);
      });
    }

    return {
      success: true,
      status: session.status,
      qr: session.qr,
    };
  }

  /**
   * Disconnect a user session
   * @param {string} userId
   * @returns {{ success: boolean, message: string }}
   */
  async disconnect(userId) {
    const session = this.sessions.get(userId);
    if (!session) {
      return { success: false, message: "Session not found" };
    }

    try {
      // Save LID cache before disconnecting
      if (session.lidCache) {
        await session.lidCache.save();
        session.logger.info({ userId }, "LID cache saved on disconnect");
      }
      session.sock.end();
      session.status = SESSION_STATUS.DISCONNECTED;
      this.sessions.delete(userId);
      return { success: true, message: "Disconnected" };
    } catch (err) {
      return { success: false, message: String(err) };
    }
  }

  /**
   * Send a message
   * @param {string} userId
   * @param {string} to - Phone number in E.164 or JID
   * @param {string} text
   * @returns {Promise<{ success: boolean, messageId?: string, error?: string }>}
   */
  async send(userId, to, text) {
    const session = this.sessions.get(userId);
    if (!session) {
      return { success: false, error: "Session not found" };
    }
    if (session.status !== SESSION_STATUS.CONNECTED) {
      return { success: false, error: `Not connected (status: ${session.status})` };
    }

    try {
      const jid = toWhatsappJid(to);
      if (!jid) {
        return { success: false, error: "Invalid recipient" };
      }

      const result = await session.sock.sendMessage(jid, { text });
      return { success: true, messageId: result?.key?.id };
    } catch (err) {
      return { success: false, error: String(err) };
    }
  }

  /**
   * Get session status
   * @param {string} userId
   * @returns {{ status: string, phone?: string, qr?: string, lidCacheStats?: object }}
   */
  getStatus(userId) {
    const session = this.sessions.get(userId);
    if (!session) {
      return { status: SESSION_STATUS.DISCONNECTED };
    }

    return {
      status: session.status,
      phone: session.sock?.user?.id || null,
      lid: session.sock?.user?.lid || null,
      qr: session.qr,
      lidCacheStats: session.lidCache?.getStats() || null,
    };
  }

  /**
   * Get QR code for session
   * @param {string} userId
   * @returns {{ qr: string | null, status: string }}
   */
  getQR(userId) {
    const session = this.sessions.get(userId);
    if (!session) {
      return { qr: null, status: SESSION_STATUS.DISCONNECTED };
    }

    return {
      qr: session.qr,
      status: session.status,
    };
  }

  /**
   * List all sessions
   * @returns {Array<{ userId: string, status: string, phone: string | null }>}
   */
  listSessions() {
    const result = [];
    for (const [userId, session] of this.sessions) {
      result.push({
        userId,
        status: session.status,
        phone: session.sock?.user?.id || null,
      });
    }
    return result;
  }

  /**
   * Set message handler for all sessions
   * @param {Function} handler - (userId, upsert, sock, lidCache) => void
   */
  setMessageHandler(handler) {
    this.messageHandler = handler;
    // Attach to existing sessions
    for (const [userId, session] of this.sessions) {
      session.sock.ev.on("messages.upsert", (upsert) => {
        handler(userId, upsert, session.sock, session.lidCache);
      });
    }
  }
}

export { GatewayManager, SESSION_STATUS };
