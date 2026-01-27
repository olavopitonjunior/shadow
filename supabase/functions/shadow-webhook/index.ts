import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.0";
import {
  handleCorsPreflightRequest,
  corsJsonResponse,
  corsErrorResponse,
} from "../_shared/cors.ts";
import {
  normalizeIncomingMessage,
  extractEntities,
  isLikelyTrivial,
  parseBoolean,
  type NormalizedMessage,
} from "../_shared/shadow.ts";

interface ShadowResponse {
  reply: string;
  intent: string;
  created: {
    task_id?: string;
    appointment_id?: string;
  };
  reply_target_phone?: string;
}

serve(async (req: Request) => {
  const preflight = handleCorsPreflightRequest(req);
  if (preflight) return preflight;

  if (req.method !== "POST") {
    return corsErrorResponse("Method not allowed", 405, req);
  }

  try {
    const payload = await req.json();

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    if (
      payload?.instanceId &&
      typeof payload?.type === "string" &&
      payload.type.endsWith("Callback") &&
      payload.type !== "ReceivedCallback"
    ) {
      await logWebhook(supabase, payload, null);
      return corsJsonResponse({ ok: true, ignored: payload.type }, 200, req);
    }

    if (payload?.type === "ReceivedCallback") {
      const fromMe = parseBoolean(payload?.fromMe);
      const fromApi = parseBoolean(payload?.fromApi);
      if (fromMe || fromApi) {
        await logWebhook(supabase, payload, null);
        return corsJsonResponse({ ok: true, ignored: "fromMe" }, 200, req);
      }
      const messageId = payload?.messageId ?? payload?.id ?? payload?.ids?.[0];
      if (messageId) {
        const { data: existing } = await supabase
          .from("shadow_webhook_logs")
          .select("id")
          .eq("payload->>messageId", String(messageId))
          .limit(1);
        if (existing && existing.length > 0) {
          await logWebhook(supabase, payload, null);
          return corsJsonResponse({ ok: true, ignored: "duplicate" }, 200, req);
        }
      }
    }

    let message: NormalizedMessage | null = null;
    try {
      message = normalizeIncomingMessage(payload);
    } finally {
      await logWebhook(supabase, payload, message);
    }
    if (!message) {
      throw new Error("Unsupported payload format");
    }

    const config = await fetchShadowConfig(supabase);
    const ownerPhone = config.owner_phone || Deno.env.get("SHADOW_OWNER_PHONE") || message.user_phone;

    if (config.ignore_groups && message.is_group) {
      return corsJsonResponse({ ok: true, ignored: "group" }, 200, req);
    }

    const result = await handleShadowMessage(supabase, message, ownerPhone, config);

    // Optional: send reply via gateway if configured
    if (config.enable_shadow_replies && result.reply && result.reply_target_phone) {
      await trySendReply(result.reply_target_phone, result.reply, config);
    }

    return corsJsonResponse(
      {
        ok: true,
        reply: result.reply,
        intent: result.intent,
        created: result.created,
      },
      200,
      req
    );
  } catch (error) {
    return corsErrorResponse(
      error instanceof Error ? error.message : "Internal error",
      500,
      req
    );
  }
});

async function logWebhook(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  payload: unknown,
  message: NormalizedMessage | null
) {
  try {
    const fallbackDirection =
      (payload as any)?.fromMe === true ? "outbound" : (payload as any)?.fromMe === false ? "inbound" : null;
    await supabase.from("shadow_webhook_logs").insert({
      source: message?.source ?? (payload as any)?.source ?? null,
      user_phone: message?.user_phone ?? null,
      contact_phone: message?.contact_phone ?? null,
      direction: message?.direction ?? fallbackDirection,
      content: message?.content ?? null,
      content_type: message?.content_type ?? null,
      is_group: message?.is_group ?? (payload as any)?.isGroup ?? null,
      payload,
    });
  } catch {
    // ignore logging errors to avoid breaking webhook
  }
}

async function handleShadowMessage(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  message: NormalizedMessage,
  ownerPhone: string,
  config: ShadowConfig
): Promise<ShadowResponse> {
  const user = await ensureUser(supabase, ownerPhone);
  const senderPhone = message.contact_phone ?? "";
  const isOwner = normalizePhone(senderPhone) === normalizePhone(ownerPhone);

  if (!isOwner) {
    const processed = await processContactMessage(
      supabase,
      user.id,
      senderPhone,
      message,
      config
    );
    return { reply: "", intent: processed.intent, created: processed.created };
  }

  if (message.direction === "outbound") {
    // Shadow messages sent to owner should not be reprocessed
    return { reply: "", intent: "ignored", created: {} };
  }

  const resolvedText = (await resolveContentText(message)) || message.content;
  if (await isRecentEcho(supabase, user.id, resolvedText)) {
    return { reply: "", intent: "ignored", created: {} };
  }

  const contact = await ensureContact(
    supabase,
    user.id,
    senderPhone,
    "Shadow"
  );
  const conversation = await ensureConversation(supabase, user.id, contact.id);
  await insertMessage(
    supabase,
    conversation.id,
    "inbound",
    { ...message, content: resolvedText } as NormalizedMessage
  );

  const extracted = extractEntities(resolvedText);
  const created: ShadowResponse["created"] = {};

  let reply = "Entendi. Posso ajudar com algo mais?";

  if (extracted.intent === "list_tasks") {
    const tasks = await listPendingTasks(supabase, user.id);
    if (tasks.length === 0) {
      reply = "Voce nao tem tarefas pendentes.";
    } else {
      const lines = tasks.map((t: any, idx: number) => `${idx + 1}. ${t.title}`);
      reply = `Tarefas pendentes:\n${lines.join("\n")}`;
    }
  } else if (extracted.intent === "list_appointments") {
    const items = await listUpcomingAppointments(supabase, user.id);
    if (items.length === 0) {
      reply = "Nao encontrei compromissos futuros.";
    } else {
      const lines = items.map((a: any, idx: number) => {
        const when = a.scheduled_at ? a.scheduled_at.slice(0, 16).replace("T", " ") : "";
        return `${idx + 1}. ${a.title} - ${when}`;
      });
      reply = `Proximos compromissos:\n${lines.join("\n")}`;
    }
  } else if (extracted.intent === "create_task") {
    const title = extracted.task_title || "Nova tarefa";
    const task = await createTask(supabase, user.id, null, title, null);
    created.task_id = task.id;
    reply = `Tarefa criada: ${title}`;
  } else if (extracted.intent === "create_appointment") {
    if (extracted.needs_clarification || !extracted.appointment_time) {
      reply = "Qual dia e horario para o compromisso?";
    } else {
      const title = extracted.appointment_title || "Compromisso";
      const appointment = await createAppointment(
        supabase,
        user.id,
        null,
        title,
        extracted.appointment_time
      );
      created.appointment_id = appointment.id;
      reply = `Compromisso agendado: ${title}`;
    }
  } else {
    reply = "Anotado. Posso ajudar com tarefas ou compromissos se precisar.";
  }

  if (config.enable_shadow_replies) {
    await insertMessage(
      supabase,
      conversation.id,
      "outbound",
      {
        ...message,
        direction: "outbound",
        content: reply,
      } as NormalizedMessage
    );

    await insertInteraction(supabase, user.id, message.content, reply, extracted.intent, created);

    return {
      reply,
      intent: extracted.intent,
      created,
      reply_target_phone: senderPhone,
    } as ShadowResponse & { reply_target_phone: string };
  }

  await insertInteraction(supabase, user.id, message.content, "", extracted.intent, created);
  return { reply: "", intent: extracted.intent, created };
}

async function ensureUser(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  phone: string
) {
  const { data: existing } = await supabase
    .from("shadow_users")
    .select("*")
    .eq("phone_number", phone)
    .maybeSingle();
  if (existing) return existing;

  const { data, error } = await supabase
    .from("shadow_users")
    .insert({ phone_number: phone })
    .select()
    .single();
  if (error) throw error;
  return data;
}

async function ensureContact(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string,
  phone: string,
  name: string | null
) {
  const { data: existing } = await supabase
    .from("shadow_contacts")
    .select("*")
    .eq("user_id", userId)
    .eq("phone_number", phone)
    .maybeSingle();
  if (existing) return existing;

  const { data, error } = await supabase
    .from("shadow_contacts")
    .insert({
      user_id: userId,
      phone_number: phone,
      name: name || "Contato",
    })
    .select()
    .single();
  if (error) throw error;
  return data;
}

async function ensureConversation(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string,
  contactId: string
) {
  const { data: existing } = await supabase
    .from("shadow_conversations")
    .select("*")
    .eq("user_id", userId)
    .eq("contact_id", contactId)
    .maybeSingle();
  if (existing) return existing;

  const { data, error } = await supabase
    .from("shadow_conversations")
    .insert({
      user_id: userId,
      contact_id: contactId,
      started_at: new Date().toISOString(),
      last_message_at: new Date().toISOString(),
    })
    .select()
    .single();
  if (error) throw error;
  return data;
}

async function insertMessage(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  conversationId: string,
  direction: "inbound" | "outbound",
  message: NormalizedMessage
) {
  const { error } = await supabase.from("shadow_messages").insert({
    conversation_id: conversationId,
    direction,
    content: message.content,
    content_type: message.content_type ?? "text",
    timestamp: message.timestamp ?? new Date().toISOString(),
  });
  if (error) throw error;

  await supabase
    .from("shadow_conversations")
    .update({ last_message_at: new Date().toISOString() })
    .eq("id", conversationId);
}

async function createTask(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string,
  contactId: string | null,
  title: string,
  dueDate: Date | null
) {
  const { data, error } = await supabase
    .from("shadow_tasks")
    .insert({
      user_id: userId,
      contact_id: contactId,
      title,
      due_date: dueDate ? dueDate.toISOString() : null,
    })
    .select()
    .single();
  if (error) throw error;
  return data;
}

async function createAppointment(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string,
  contactId: string | null,
  title: string,
  scheduledAt: Date
) {
  const { data, error } = await supabase
    .from("shadow_appointments")
    .insert({
      user_id: userId,
      contact_id: contactId,
      title,
      scheduled_at: scheduledAt.toISOString(),
    })
    .select()
    .single();
  if (error) throw error;
  return data;
}

async function listPendingTasks(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string
) {
  const { data, error } = await supabase
    .from("shadow_tasks")
    .select("id,title,due_date,status")
    .eq("user_id", userId)
    .eq("status", "pending")
    .order("created_at", { ascending: false })
    .limit(10);
  if (error) throw error;
  return data ?? [];
}

async function listUpcomingAppointments(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string
) {
  const nowIso = new Date().toISOString();
  const { data, error } = await supabase
    .from("shadow_appointments")
    .select("id,title,scheduled_at,status")
    .eq("user_id", userId)
    .gte("scheduled_at", nowIso)
    .order("scheduled_at", { ascending: true })
    .limit(10);
  if (error) throw error;
  return data ?? [];
}

async function insertInteraction(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string,
  userMessage: string,
  shadowResponse: string,
  intent: string,
  created: Record<string, string | undefined>
) {
  await supabase.from("shadow_interactions").insert({
    user_id: userId,
    user_message: userMessage,
    shadow_response: shadowResponse,
    intent,
    entities_created: created,
  });
}

async function processContactMessage(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string,
  senderPhone: string,
  message: NormalizedMessage,
  config: ShadowConfig
): Promise<{ intent: string; created: Record<string, string | undefined> }> {
  const contentText = await resolveContentText(message);
  if (!contentText || isLikelyTrivial(contentText)) {
    return { intent: "ignored", created: {} };
  }

  const analysis = await analyzeWithGemini(contentText);
  if (config.store_relevant_only && !analysis.relevant) {
    return { intent: "ignored", created: {} };
  }

  const contact = await ensureContact(
    supabase,
    userId,
    senderPhone,
    analysis.contact_name ?? "Contato"
  );
  const conversation = await ensureConversation(supabase, userId, contact.id);

  const summary = analysis.summary || contentText;
  await insertMessage(
    supabase,
    conversation.id,
    message.direction === "outbound" ? "outbound" : "inbound",
    {
      ...message,
      content: summary,
    } as NormalizedMessage
  );

  const created: Record<string, string | undefined> = {};

  if (analysis.task_title) {
    const task = await createTask(supabase, userId, contact.id, analysis.task_title, null);
    created.task_id = task.id;
  }

  if (analysis.appointment_title && analysis.appointment_time) {
    const appointment = await createAppointment(
      supabase,
      userId,
      contact.id,
      analysis.appointment_title,
      analysis.appointment_time
    );
    created.appointment_id = appointment.id;
  }

  return { intent: analysis.intent, created };
}

async function trySendReply(targetPhone: string, reply: string, config: ShadowConfig) {
  const gatewayUrl = Deno.env.get("EVOLUTION_API_URL") || config.evolution_api_url;
  const gatewayKey = Deno.env.get("EVOLUTION_API_KEY") || config.evolution_api_key;
  const instance = Deno.env.get("EVOLUTION_INSTANCE_ID") || config.evolution_instance_id;

  if (gatewayUrl && gatewayKey && instance) {
    if (!targetPhone) return;
    const body = {
      number: targetPhone,
      text: reply,
    };

    await fetch(`${gatewayUrl}/message/sendText/${instance}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "apikey": gatewayKey,
      },
      body: JSON.stringify(body),
    });
    return;
  }

  const zapiInstance = Deno.env.get("ZAPI_INSTANCE_ID");
  const zapiToken = Deno.env.get("ZAPI_TOKEN");
  const zapiClientToken = Deno.env.get("ZAPI_CLIENT_TOKEN");
  const zapiBaseUrl = Deno.env.get("ZAPI_BASE_URL") || "https://api.z-api.io";

  if (!zapiInstance || !zapiToken || !zapiClientToken) return;
  if (!targetPhone) return;

  const body = {
    phone: normalizePhone(targetPhone),
    message: reply,
  };

  await fetch(`${zapiBaseUrl}/instances/${zapiInstance}/token/${zapiToken}/send-text`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Client-Token": zapiClientToken,
    },
    body: JSON.stringify(body),
  });
}

interface ShadowConfig {
  owner_phone: string | null;
  ignore_groups: boolean;
  store_relevant_only: boolean;
  enable_shadow_replies: boolean;
  evolution_api_url?: string | null;
  evolution_api_key?: string | null;
  evolution_instance_id?: string | null;
}

async function fetchShadowConfig(
  // deno-lint-ignore no-explicit-any
  supabase: any
): Promise<ShadowConfig> {
  const { data } = await supabase.from("shadow_config").select("*").limit(1).maybeSingle();
  if (data) {
    return {
      owner_phone: data.owner_phone ?? null,
      ignore_groups: data.ignore_groups ?? true,
      store_relevant_only: data.store_relevant_only ?? true,
      enable_shadow_replies: data.enable_shadow_replies ?? true,
      evolution_api_url: data.evolution_api_url ?? null,
      evolution_api_key: data.evolution_api_key ?? null,
      evolution_instance_id: data.evolution_instance_id ?? null,
    };
  }

  const defaults = {
    owner_phone: null,
    ignore_groups: true,
    store_relevant_only: true,
    enable_shadow_replies: true,
    evolution_api_url: null,
    evolution_api_key: null,
    evolution_instance_id: null,
  };
  await supabase.from("shadow_config").insert(defaults);
  return defaults;
}

function normalizePhone(phone: string | null): string {
  if (!phone) return "";
  return phone.replace(/[^\d]/g, "");
}

async function resolveContentText(message: NormalizedMessage): Promise<string> {
  if (message.content && message.content.trim()) return message.content;

  const mediaUrl = extractMediaUrl(message.raw);
  if (!mediaUrl) return "";

  try {
    const res = await fetch(mediaUrl);
    if (!res.ok) return "";
    const bytes = new Uint8Array(await res.arrayBuffer());
    const b64 = btoa(String.fromCharCode(...bytes));
    const mime = res.headers.get("content-type") || "application/octet-stream";
    return await analyzeMediaWithGemini(b64, mime);
  } catch {
    return "";
  }
}

function extractMediaUrl(raw: unknown): string | null {
  const payload = raw as any;
  return (
    payload?.media_url ??
    payload?.media?.url ??
    payload?.url ??
    payload?.image?.imageUrl ??
    payload?.audio?.audioUrl ??
    payload?.video?.videoUrl ??
    payload?.document?.documentUrl ??
    payload?.data?.message?.imageMessage?.url ??
    payload?.data?.message?.audioMessage?.url ??
    null
  );
}

async function analyzeWithGemini(text: string): Promise<{
  relevant: boolean;
  summary: string | null;
  intent: string;
  contact_name?: string | null;
  company?: string | null;
  task_title?: string | null;
  appointment_title?: string | null;
  appointment_time?: Date | null;
}> {
  const apiKey = Deno.env.get("GEMINI_API_KEY");
  if (!apiKey) {
    return {
      relevant: !isLikelyTrivial(text),
      summary: text,
      intent: "note",
    };
  }

  const prompt = `
Voce e um assistente que decide se uma mensagem de WhatsApp contem informacao relevante para um CRM pessoal.
Retorne JSON com:
{
  "relevant": boolean,
  "summary": "resumo curto",
  "intent": "note" | "task" | "appointment" | "contact",
  "contact_name": "nome ou null",
  "company": "empresa ou null",
  "task_title": "tarefa ou null",
  "appointment_title": "titulo ou null",
  "appointment_time": "ISO8601 ou null"
}

Mensagem:
"""${text}"""
`;

  const body = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.2,
      maxOutputTokens: 512,
    },
  };

  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );

  if (!res.ok) {
    return { relevant: !isLikelyTrivial(text), summary: text, intent: "note" };
  }

  const data = await res.json();
  const textOut = data?.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
  const jsonMatch = textOut.match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    return { relevant: !isLikelyTrivial(text), summary: text, intent: "note" };
  }
  const parsed = JSON.parse(jsonMatch[0]);

  return {
    relevant: Boolean(parsed.relevant),
    summary: parsed.summary ?? null,
    intent: parsed.intent ?? "note",
    contact_name: parsed.contact_name ?? null,
    company: parsed.company ?? null,
    task_title: parsed.task_title ?? null,
    appointment_title: parsed.appointment_title ?? null,
    appointment_time: parsed.appointment_time ? new Date(parsed.appointment_time) : null,
  };
}

async function analyzeMediaWithGemini(base64: string, mime: string): Promise<string> {
  const apiKey = Deno.env.get("GEMINI_API_KEY");
  if (!apiKey) return "";

  const isAudio = mime.startsWith("audio/");
  const instruction = isAudio
    ? "Transcreva o audio e destaque informacoes relevantes para CRM."
    : "Descreva de forma objetiva o conteudo relevante para CRM.";

  const body = {
    contents: [
      {
        parts: [
          { text: instruction },
          { inlineData: { data: base64, mimeType: mime } },
        ],
      },
    ],
    generationConfig: {
      temperature: 0.2,
      maxOutputTokens: 256,
    },
  };

  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );

  if (!res.ok) return "";
  const data = await res.json();
  return data?.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
}

async function isRecentEcho(
  // deno-lint-ignore no-explicit-any
  supabase: any,
  userId: string,
  text: string,
  windowMs = 2 * 60 * 1000
) {
  const normalized = normalizeText(text);
  if (!normalized) return false;

  const { data } = await supabase
    .from("shadow_interactions")
    .select("shadow_response,timestamp")
    .eq("user_id", userId)
    .order("timestamp", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (!data?.shadow_response || !data?.timestamp) return false;
  const last = normalizeText(data.shadow_response);
  if (!last || last !== normalized) return false;

  const age = Date.now() - new Date(data.timestamp).getTime();
  return age >= 0 && age <= windowMs;
}

function normalizeText(text: string) {
  return text.trim().toLowerCase();
}
