export type ContentType = "text" | "audio" | "image" | "document";
export type Direction = "inbound" | "outbound";

export interface NormalizedMessage {
  user_phone: string;
  contact_phone: string | null;
  direction: Direction;
  content: string;
  content_type: ContentType;
  timestamp: string;
  source: string;
  is_group: boolean;
  raw: unknown;
}

export interface ExtractedEntityResult {
  intent: "list_tasks" | "list_appointments" | "create_task" | "create_appointment" | "note";
  task_title?: string | null;
  appointment_title?: string | null;
  appointment_time?: Date | null;
  needs_clarification?: boolean;
}

export function parseBoolean(value: unknown): boolean {
  if (value === true || value === 1) return true;
  if (value === false || value === 0 || value === null || value === undefined) return false;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return false;
    if (["true", "1", "yes", "y", "sim"].includes(normalized)) return true;
    if (["false", "0", "no", "n", "nao", "não"].includes(normalized)) return false;
  }
  return Boolean(value);
}

export function normalizeIncomingMessage(payload: any): NormalizedMessage {
  const nowIso = new Date().toISOString();

  // Generic payload
  if (payload?.user_phone && (payload?.content || payload?.text)) {
    return {
      user_phone: String(payload.user_phone),
      contact_phone: payload.contact_phone ? String(payload.contact_phone) : null,
      direction: payload.direction === "outbound" ? "outbound" : "inbound",
      content: String(payload.content ?? payload.text ?? ""),
      content_type: payload.content_type ?? "text",
      timestamp: payload.timestamp ?? nowIso,
      source: payload.source ?? "generic",
      is_group: Boolean(payload.is_group),
      raw: payload,
    };
  }

  // Z-API webhook (ReceivedCallback only)
  if (payload?.type === "ReceivedCallback" && payload?.phone && payload?.momment) {
    const isGroup = Boolean(payload?.isGroup);
    const fromMe = parseBoolean(payload?.fromMe);
    const content =
      payload?.text?.message ??
      payload?.listResponseMessage?.message ??
      payload?.image?.caption ??
      payload?.video?.caption ??
      payload?.document?.caption ??
      "";
    const timestamp = payload?.momment
      ? new Date(Number(payload.momment)).toISOString()
      : nowIso;
    const contactPhone = isGroup
      ? payload?.participantPhone ?? payload?.phone
      : payload?.phone;
    return {
      user_phone: String(payload?.connectedPhone ?? payload?.instanceId ?? "unknown"),
      contact_phone: contactPhone ? String(contactPhone) : null,
      direction: fromMe ? "outbound" : "inbound",
      content: String(content),
      content_type: detectZapiContentType(payload),
      timestamp,
      source: "zapi",
      is_group: isGroup,
      raw: payload,
    };
  }

  // WhatsApp Business API / 360dialog style
  const businessValue = payload?.entry?.[0]?.changes?.[0]?.value;
  if (businessValue?.messages?.[0]) {
    const msg = businessValue.messages[0];
    const content =
      msg?.text?.body ??
      msg?.button?.text ??
      msg?.interactive?.button_reply?.title ??
      msg?.interactive?.list_reply?.title ??
      "";
    const timestamp = msg?.timestamp
      ? new Date(Number(msg.timestamp) * 1000).toISOString()
      : nowIso;
    return {
      user_phone: String(
        businessValue?.metadata?.display_phone_number ??
          businessValue?.metadata?.phone_number_id ??
          "unknown"
      ),
      contact_phone: msg?.from ? String(msg.from) : null,
      direction: "inbound",
      content: String(content),
      content_type: "text",
      timestamp,
      source: "whatsapp_business",
      is_group: false,
      raw: payload,
    };
  }

  // Evolution / Baileys style (best effort)
  const evo = payload?.data ?? payload;
  if (evo?.key?.remoteJid) {
    const remoteJid = String(evo.key.remoteJid);
    const fromMe = parseBoolean(evo.key.fromMe);
    const participant = evo.key.participant ? String(evo.key.participant) : remoteJid;
    const isGroup = remoteJid.endsWith("@g.us");
    const content =
      evo?.message?.conversation ??
      evo?.message?.extendedTextMessage?.text ??
      evo?.message?.imageMessage?.caption ??
      evo?.message?.videoMessage?.caption ??
      "";
    const timestamp = evo?.messageTimestamp
      ? new Date(Number(evo.messageTimestamp) * 1000).toISOString()
      : nowIso;
    return {
      user_phone: String(payload?.user_phone ?? evo?.user_phone ?? evo?.owner ?? "unknown"),
      contact_phone: participant || null,
      direction: fromMe ? "outbound" : "inbound",
      content: String(content),
      content_type: detectEvolutionContentType(evo),
      timestamp,
      source: "evolution",
      is_group: isGroup,
      raw: payload,
    };
  }

  throw new Error("Unsupported payload format");
}

function detectEvolutionContentType(evo: any): ContentType {
  if (evo?.message?.audioMessage) return "audio";
  if (evo?.message?.imageMessage) return "image";
  if (evo?.message?.documentMessage) return "document";
  return "text";
}

function detectZapiContentType(payload: any): ContentType {
  if (payload?.audio?.audioUrl) return "audio";
  if (payload?.image?.imageUrl || payload?.video?.videoUrl) return "image";
  if (payload?.document?.documentUrl) return "document";
  return "text";
}

export function extractEntities(text: string): ExtractedEntityResult {
  const normalized = normalizeForIntent(text);
  const intent = detectIntent(normalized);
  const appointmentTime = intent === "create_appointment" ? parseDateTime(text) : null;

  const result: ExtractedEntityResult = {
    intent,
    task_title: null,
    appointment_title: null,
    appointment_time: appointmentTime,
    needs_clarification: false,
  };

  if (intent === "create_task") {
    result.task_title = guessTitle(text, 120);
  }

  if (intent === "create_appointment") {
    result.appointment_title = guessTitle(text, 120) || "Reuniao";
    if (!appointmentTime) {
      result.needs_clarification = true;
    }
  }

  return result;
}

export function isLikelyTrivial(text: string): boolean {
  const trimmed = text.trim().toLowerCase();
  if (!trimmed) return true;
  if (trimmed.length < 8) return true;
  const trivial = [
    "ok",
    "obrigado",
    "valeu",
    "beleza",
    "blz",
    "bom dia",
    "boa tarde",
    "boa noite",
    "👍",
    "✅",
  ];
  return trivial.some((phrase) => trimmed === phrase);
}

function detectIntent(lower: string): ExtractedEntityResult["intent"] {
  if (lower.includes("tarefas") || lower.startsWith("tarefa")) {
    return "list_tasks";
  }
  if (lower.includes("agenda") || lower.includes("compromisso") || lower.includes("reunioes")) {
    return "list_appointments";
  }
  if (
    lower.includes("reuniao") ||
    lower.includes("call") ||
    lower.includes("meeting") ||
    lower.includes("agendar") ||
    lower.includes("agende") ||
    lower.includes("marcar") ||
    lower.includes("marque")
  ) {
    return "create_appointment";
  }
  if (
    lower.includes("lembra") ||
    lower.includes("lembrete") ||
    lower.includes("preciso") ||
    lower.includes("enviar") ||
    lower.includes("ligar") ||
    lower.includes("follow")
  ) {
    return "create_task";
  }
  return "note";
}

function guessTitle(text: string, maxLen: number): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return trimmed.length > maxLen ? `${trimmed.slice(0, maxLen)}...` : trimmed;
}

function parseDateTime(text: string): Date | null {
  const lower = normalizeForIntent(text);
  const now = new Date();
  let date = new Date(now);

  if (lower.includes("amanha")) {
    date.setDate(date.getDate() + 1);
  }

  const dateMatch = text.match(/\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b/);
  if (dateMatch) {
    const day = Number(dateMatch[1]);
    const month = Number(dateMatch[2]) - 1;
    const year = dateMatch[3] ? Number(dateMatch[3]) : now.getFullYear();
    date = new Date(year, month, day);
  }

  const timeMatch = text.match(/\b(\d{1,2})(?:[:h](\d{2}))?\b/);
  if (timeMatch) {
    const hours = Number(timeMatch[1]);
    const minutes = timeMatch[2] ? Number(timeMatch[2]) : 0;
    date.setHours(hours, minutes, 0, 0);
    return date;
  }

  if (lower.includes("hoje") || lower.includes("amanha") || dateMatch) {
    return date;
  }

  return null;
}

function normalizeForIntent(text: string) {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}
