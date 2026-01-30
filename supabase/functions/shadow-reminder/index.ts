/**
 * Shadow Reminder Edge Function
 *
 * Processa lembretes pendentes e envia via WhatsApp.
 * Suporta Evolution API e Z-API como gateways.
 */

import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.0";
import {
  handleCorsPreflightRequest,
  corsJsonResponse,
  corsErrorResponse,
} from "../_shared/cors.ts";

interface ShadowConfig {
  owner_phone?: string;
  evolution_api_url?: string;
  evolution_api_key?: string;
  evolution_instance?: string;
  zapi_instance_id?: string;
  zapi_token?: string;
  enable_shadow_replies?: boolean;
}

interface SendResult {
  reminder_id: string;
  success: boolean;
  error?: string;
}

/**
 * Envia mensagem via Evolution API
 */
async function sendViaEvolution(
  config: ShadowConfig,
  phone: string,
  message: string
): Promise<boolean> {
  if (!config.evolution_api_url || !config.evolution_api_key || !config.evolution_instance) {
    console.log("[reminder] Evolution API not configured");
    return false;
  }

  const url = `${config.evolution_api_url}/message/sendText/${config.evolution_instance}`;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: config.evolution_api_key,
      },
      body: JSON.stringify({
        number: phone.replace(/\D/g, ""),
        text: message,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[reminder] Evolution API error:", errorText);
      return false;
    }

    console.log("[reminder] Message sent via Evolution API");
    return true;
  } catch (error) {
    console.error("[reminder] Evolution API error:", error);
    return false;
  }
}

/**
 * Envia mensagem via Z-API
 */
async function sendViaZapi(
  config: ShadowConfig,
  phone: string,
  message: string
): Promise<boolean> {
  if (!config.zapi_instance_id || !config.zapi_token) {
    console.log("[reminder] Z-API not configured");
    return false;
  }

  const url = `https://api.z-api.io/instances/${config.zapi_instance_id}/token/${config.zapi_token}/send-text`;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        phone: phone.replace(/\D/g, ""),
        message: message,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[reminder] Z-API error:", errorText);
      return false;
    }

    console.log("[reminder] Message sent via Z-API");
    return true;
  } catch (error) {
    console.error("[reminder] Z-API error:", error);
    return false;
  }
}

/**
 * Envia mensagem usando o gateway configurado
 */
async function sendMessage(
  config: ShadowConfig,
  phone: string,
  message: string
): Promise<boolean> {
  // Tenta Evolution API primeiro
  if (config.evolution_api_url) {
    return await sendViaEvolution(config, phone, message);
  }

  // Fallback para Z-API
  if (config.zapi_instance_id) {
    return await sendViaZapi(config, phone, message);
  }

  console.log("[reminder] No WhatsApp gateway configured");
  return false;
}

serve(async (req: Request) => {
  const preflight = handleCorsPreflightRequest(req);
  if (preflight) return preflight;

  if (req.method !== "POST") {
    return corsErrorResponse("Method not allowed", 405, req);
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    // Busca configuração
    const { data: configData } = await supabase
      .from("shadow_config")
      .select("*")
      .limit(1)
      .single();

    const config: ShadowConfig = configData || {};

    if (!config.owner_phone) {
      return corsJsonResponse(
        { ok: false, error: "owner_phone not configured" },
        400,
        req
      );
    }

    // Busca lembretes pendentes
    const nowIso = new Date().toISOString();
    const { data: reminders, error } = await supabase
      .from("shadow_reminders")
      .select("*")
      .eq("sent", false)
      .lte("remind_at", nowIso)
      .limit(50);

    if (error) throw error;

    const results: SendResult[] = [];

    for (const reminder of reminders ?? []) {
      const reminderMessage = `🔔 Lembrete: ${reminder.message}`;

      // Tenta enviar via WhatsApp
      const sent = await sendMessage(config, config.owner_phone, reminderMessage);

      if (sent) {
        // Marca como enviado
        await supabase
          .from("shadow_reminders")
          .update({ sent: true })
          .eq("id", reminder.id);

        results.push({ reminder_id: reminder.id, success: true });
      } else {
        // Registra falha mas não marca como enviado (tentará novamente)
        results.push({
          reminder_id: reminder.id,
          success: false,
          error: "Failed to send message",
        });
      }
    }

    const successCount = results.filter((r) => r.success).length;
    const failCount = results.filter((r) => !r.success).length;

    return corsJsonResponse(
      {
        ok: true,
        processed_count: results.length,
        success_count: successCount,
        fail_count: failCount,
        results,
      },
      200,
      req
    );
  } catch (error) {
    console.error("[reminder] Error:", error);
    return corsErrorResponse(
      error instanceof Error ? error.message : "Internal error",
      500,
      req
    );
  }
});
