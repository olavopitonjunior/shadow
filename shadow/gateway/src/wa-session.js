import { default as makeWASocket, DisconnectReason, fetchLatestBaileysVersion, makeCacheableSignalKeyStore, useMultiFileAuthState } from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import pino from "pino";
import fs from "node:fs";
import path from "node:path";
import { config } from "./config.js";

// Persistent shadow config (group JID, etc.)
const shadowConfigPath = path.join(config.authDir, "shadow-config.json");

function loadShadowConfig() {
  try {
    if (fs.existsSync(shadowConfigPath)) {
      const data = fs.readFileSync(shadowConfigPath, "utf8");
      return JSON.parse(data);
    }
  } catch (err) {
    // Ignore errors, return empty
  }
  return {};
}

function saveShadowConfig(shadowConfig) {
  try {
    fs.mkdirSync(path.dirname(shadowConfigPath), { recursive: true });
    fs.writeFileSync(shadowConfigPath, JSON.stringify(shadowConfig, null, 2), "utf8");
  } catch (err) {
    // Ignore errors
  }
}

// Singleton para manter referência atual do socket
let currentSock = null;
let messageHandler = null;
let connectionHandler = null; // Called when connection is established

export function getCurrentSocket() {
  return currentSock;
}

export function setMessageHandler(handler) {
  messageHandler = handler;
  // Se já temos um socket, anexar o handler
  if (currentSock && handler) {
    currentSock.ev.on("messages.upsert", handler);
  }
}

/**
 * Set a handler to be called when connection is established.
 * This handler receives (sock, logger) and can set up additional event listeners.
 * Will be called on initial connect and every reconnect.
 */
export function setConnectionHandler(handler) {
  connectionHandler = handler;
}

export async function createSocket() {
  const { state, saveCreds } = await useMultiFileAuthState(config.authDir);
  const { version } = await fetchLatestBaileysVersion();
  const logger = pino({ level: config.logLevel });

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
    // Disable app state sync to avoid "tried remove, but no previous op" errors
    shouldSyncHistoryMessage: () => false,
    fireInitQueries: false,
    browser: ["shadow", "gateway", "1.0.0"],
  });

  // Atualizar referência global
  currentSock = sock;

  // Se já temos um handler de mensagens, anexar ao novo socket
  if (messageHandler) {
    sock.ev.on("messages.upsert", messageHandler);
    logger.info("Message handler reattached to new socket");
  }

  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      logger.info("WhatsApp QR recebido. Escaneie em Linked Devices.");
      qrcode.generate(qr, { small: true });
    }
    if (connection === "close") {
      const status = lastDisconnect?.error?.output?.statusCode;
      if (status === DisconnectReason.loggedOut) {
        logger.error("WhatsApp deslogou. Remova auth_info e relink.");
      } else {
        logger.warn("Conexao fechada. Reconectando...");
        createSocket().catch((err) => logger.error({ err: String(err) }, "reconnect failed"));
      }
    }
    if (connection === "open") {
      logger.info("WhatsApp conectado.");

      // Auto-create Shadow group on first connect if not configured
      const shadowConfig = loadShadowConfig();
      if (!config.shadowGroupJid && !shadowConfig.shadowGroupJid) {
        logger.info("No Shadow group configured. Auto-creating...");
        try {
          const group = await sock.groupCreate("Shadow", []);
          const groupJid = group.id;
          logger.info({ groupJid }, "Shadow group auto-created");

          // Save to persistent config
          shadowConfig.shadowGroupJid = groupJid;
          saveShadowConfig(shadowConfig);

          // Update runtime config
          config.shadowGroupJid = groupJid;

          // Send welcome message
          await sock.sendMessage(groupJid, {
            text: `[Shadow] Olá! Sou seu assistente pessoal.

Minhas mensagens sempre começam com [Shadow] para você identificar.

Comandos:
- "criar tarefa comprar leite amanhã"
- "listar tarefas"
- "agendar reunião segunda 14h"
- "listar compromissos"
- "ajuda" - ver todos os comandos

Envie uma mensagem para começar!`
          });
        } catch (err) {
          logger.error({ err: String(err) }, "Failed to auto-create Shadow group");
        }
      } else {
        // Load from persistent config if not in env
        if (!config.shadowGroupJid && shadowConfig.shadowGroupJid) {
          config.shadowGroupJid = shadowConfig.shadowGroupJid;
          logger.info({ groupJid: config.shadowGroupJid }, "Loaded Shadow group JID from config");
        }
      }

      // Call connection handler for additional event setup
      if (connectionHandler) {
        connectionHandler(sock, logger);
      }
    }
  });

  return { sock, logger };
}