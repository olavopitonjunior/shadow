#!/usr/bin/env node
/**
 * Shadow Setup CLI
 *
 * Script interativo para configurar o Shadow em um único comando.
 * Uso: node setup.js
 */

import readline from "node:readline";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

const ask = (question) =>
  new Promise((resolve) => rl.question(question, resolve));

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const GATEWAY_PORT = 18790;

function clearLine() {
  process.stdout.write("\r\x1b[K");
}

function printBox(lines, width = 60) {
  const border = "═".repeat(width);
  console.log(`╔${border}╗`);
  for (const line of lines) {
    const padding = " ".repeat(Math.max(0, width - line.length));
    console.log(`║ ${line}${padding}║`);
  }
  console.log(`╚${border}╝`);
}

async function updateEnv(filePath, key, value) {
  let content = "";
  try {
    content = await fs.readFile(filePath, "utf-8");
  } catch {
    // File doesn't exist, will create
  }

  const regex = new RegExp(`^${key}=.*$`, "m");
  if (regex.test(content)) {
    content = content.replace(regex, `${key}=${value}`);
  } else {
    content = content.trim() + `\n${key}=${value}`;
  }

  await fs.writeFile(filePath, content.trim() + "\n");
}

async function waitForConnection(maxAttempts = 120) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(`http://localhost:${GATEWAY_PORT}/status`);
      const data = await res.json();
      if (data.connected) {
        return data;
      }
    } catch {
      // Server not ready yet
    }
    await sleep(1000);
  }
  throw new Error("Timeout aguardando conexao com WhatsApp");
}

async function createShadowGroup() {
  const res = await fetch(`http://localhost:${GATEWAY_PORT}/create-shadow-group`, {
    method: "POST",
  });
  return res.json();
}

async function main() {
  console.clear();
  console.log("\n");
  printBox([
    "SHADOW SETUP",
    "",
    "Assistente pessoal no WhatsApp",
  ]);
  console.log("\n");

  // ═══════════════════════════════════════════════════════════
  // PASSO 1: Numero do WhatsApp
  // ═══════════════════════════════════════════════════════════
  console.log("Passo 1/4: Configuracao");
  console.log("─".repeat(50));

  const phoneInput = await ask("Digite seu numero WhatsApp (ex: +5511999999999): ");
  const normalized = "+" + phoneInput.replace(/\D/g, "");

  if (normalized.length < 10) {
    console.log("\n⚠ Numero invalido. Use formato: +5511999999999\n");
    rl.close();
    process.exit(1);
  }

  // Atualiza .env do gateway e agent
  const gatewayEnv = path.join(__dirname, "gateway", ".env");
  const agentEnv = path.join(__dirname, "agent", ".env");

  await updateEnv(gatewayEnv, "SHADOW_OWNER_E164", normalized);
  await updateEnv(agentEnv, "SHADOW_OWNER_E164", normalized);

  console.log(`\n✓ Numero configurado: ${normalized}\n`);

  // ═══════════════════════════════════════════════════════════
  // PASSO 2: Instrucoes pre-QR
  // ═══════════════════════════════════════════════════════════
  console.log("Passo 2/4: Preparacao");
  console.log("─".repeat(50));
  console.log("\nIMPORTANTE: Antes de continuar, adicione seu proprio");
  console.log("numero aos contatos do WhatsApp.");
  console.log("\n  WhatsApp > Contatos > Adicionar > Seu numero\n");
  console.log("Isso e necessario para as mensagens funcionarem.\n");

  await ask("Pressione ENTER quando estiver pronto...");

  // ═══════════════════════════════════════════════════════════
  // PASSO 3: Iniciar Gateway e mostrar QR
  // ═══════════════════════════════════════════════════════════
  console.log("\nPasso 3/4: Conectar WhatsApp");
  console.log("─".repeat(50));
  console.log("\nIniciando gateway...\n");

  // Spawn gateway process
  const gatewayProcess = spawn("node", ["src/index.js"], {
    cwd: path.join(__dirname, "gateway"),
    stdio: ["inherit", "inherit", "inherit"],
    env: { ...process.env },
  });

  gatewayProcess.on("error", (err) => {
    console.error("Erro ao iniciar gateway:", err.message);
    process.exit(1);
  });

  // Aguarda conexao
  console.log("Aguardando QR code... (escaneie com WhatsApp)\n");

  let status;
  try {
    status = await waitForConnection();
  } catch (err) {
    console.error("\n⚠ " + err.message);
    console.log("Verifique se o QR code foi escaneado corretamente.\n");
    gatewayProcess.kill();
    rl.close();
    process.exit(1);
  }

  console.log("\n✓ WhatsApp conectado!\n");

  // ═══════════════════════════════════════════════════════════
  // PASSO 4: Criar grupo Shadow
  // ═══════════════════════════════════════════════════════════
  console.log("Passo 4/4: Criar Grupo Shadow");
  console.log("─".repeat(50));
  console.log("\nCriando grupo Shadow...");

  try {
    const group = await createShadowGroup();

    if (group.success) {
      console.log("✓ Grupo criado: " + group.groupName);
      console.log("✓ Mensagem de boas-vindas enviada!\n");
    } else {
      console.log("⚠ Aviso: " + (group.error || "Erro desconhecido"));
      console.log("  Voce pode criar o grupo manualmente.\n");
    }
  } catch (err) {
    console.log("⚠ Erro ao criar grupo: " + err.message);
    console.log("  Voce pode criar o grupo manualmente.\n");
  }

  // ═══════════════════════════════════════════════════════════
  // SETUP COMPLETO
  // ═══════════════════════════════════════════════════════════
  console.log("═".repeat(60));
  console.log("\n✅ SETUP COMPLETO!\n");

  printBox([
    "Abra o grupo 'Shadow' no WhatsApp para comecar!",
    "",
    "Comandos disponiveis:",
    "  tarefa: descricao     - criar tarefa",
    "  lembrete: msg em hora - criar lembrete",
    "  mostrar tarefas       - listar pendencias",
    "  ajuda                 - ver todos comandos",
  ]);

  console.log("\nShadow esta rodando. Pressione Ctrl+C para parar.\n");

  rl.close();

  // Mantem o processo rodando
  process.on("SIGINT", () => {
    console.log("\n\nEncerrando Shadow...");
    gatewayProcess.kill();
    process.exit(0);
  });
}

main().catch((err) => {
  console.error("\n⚠ Erro no setup:", err.message);
  rl.close();
  process.exit(1);
});
