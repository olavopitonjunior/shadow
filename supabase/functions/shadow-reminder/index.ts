/**
 * DEPRECATED: This function is being migrated to local scheduler.py
 * See shadow/agent/scheduler.py for the new implementation.
 * Kept for potential Business API integration in SaaS version.
 *
 * This file depends on Evolution/Z-API adapters which have been removed.
 * The local Baileys gateway is now the primary integration.
 *
 * Original description:
 * Shadow Reminder Edge Function - Processa lembretes pendentes e envia via WhatsApp.
 */

import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.0";
import {
  handleCorsPreflightRequest,
  corsJsonResponse,
  corsErrorResponse,
} from "../_shared/cors.ts";
import {
  resolveAdapter,
  sendTextWithFallback,
  type ShadowConfig,
  type SendResult as AdapterSendResult,
} from "../_shared/adapters/index.ts";
import {
  resolveRecipient,
  type RecipientContext,
  type ResolvedRecipient,
} from "../_shared/recipient-resolver.ts";
import { decryptText } from "../_shared/crypto.ts";

interface ReminderSendResult {
  reminder_id: string;
  success: boolean;
  error?: string;
  attempts?: number;
  adapter?: string;
  /** How recipient was resolved (Phase 4) */
  recipient_source?: string;
  /** Target phone used */
  recipient?: string;
}

interface RetryPolicy {
  maxAttempts: number;
  initialDelayMs: number;
  backoffMultiplier: number;
  maxDelayMs: number;
}

const DEFAULT_RETRY_POLICY: RetryPolicy = {
  maxAttempts: 3,
  initialDelayMs: 1000,
  backoffMultiplier: 2,
  maxDelayMs: 30000,
};

/**
 * Aguarda um período de tempo (para retry backoff)
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Calcula o delay para a próxima tentativa usando backoff exponencial
 */
function calculateBackoffDelay(attempt: number, policy: RetryPolicy): number {
  const delay = policy.initialDelayMs * Math.pow(policy.backoffMultiplier, attempt - 1);
  return Math.min(delay, policy.maxDelayMs);
}

/**
 * Envia mensagem com retry e backoff exponencial usando adapters
 */
async function sendMessageWithRetry(
  config: ShadowConfig & { owner_phone?: string },
  phone: string,
  message: string,
  policy: RetryPolicy = DEFAULT_RETRY_POLICY
): Promise<{ success: boolean; attempts: number; lastError?: string; adapter?: string }> {
  let lastError: string | undefined;
  let lastAdapter: string | undefined;

  for (let attempt = 1; attempt <= policy.maxAttempts; attempt++) {
    console.log(`[reminder] Attempt ${attempt}/${policy.maxAttempts}`);

    // Usa sendTextWithFallback para tentar todos os adapters disponíveis
    const result = await sendTextWithFallback(config, phone, message);
    lastAdapter = result.adapter;

    if (result.success) {
      console.log(`[reminder] Message sent via ${result.adapter} on attempt ${attempt}`);
      return { success: true, attempts: attempt, adapter: result.adapter };
    }

    lastError = result.error;
    console.log(`[reminder] Attempt ${attempt} failed: ${lastError}`);

    // Se não é a última tentativa, aguarda antes de retry
    if (attempt < policy.maxAttempts) {
      const delay = calculateBackoffDelay(attempt, policy);
      console.log(`[reminder] Waiting ${delay}ms before retry...`);
      await sleep(delay);
    }
  }

  return {
    success: false,
    attempts: policy.maxAttempts,
    lastError,
    adapter: lastAdapter,
  };
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

    const config = (configData || {}) as ShadowConfig & { owner_phone?: string };

    // Note: owner_phone is now optional as reminders can have their own target_phone
    // But we warn if neither is available as a fallback
    if (!config.owner_phone) {
      console.warn("[reminder] No owner_phone configured - reminders without target_phone will fail");
    }

    // Verifica se há pelo menos um adapter configurado
    const adapter = resolveAdapter(config);
    if (!adapter) {
      return corsJsonResponse(
        { ok: false, error: "No WhatsApp gateway configured (Evolution API or Z-API)" },
        400,
        req
      );
    }

    // Busca lembretes pendentes (excluindo falhas permanentes)
    const nowIso = new Date().toISOString();
    const { data: reminders, error } = await supabase
      .from("shadow_reminders")
      .select("*")
      .eq("sent", false)
      .eq("failed", false)
      .lte("remind_at", nowIso)
      .limit(50);

    if (error) throw error;

    const results: ReminderSendResult[] = [];

    for (const reminder of reminders ?? []) {
      const decrypted = await decryptText(reminder.message ?? "", reminder.user_id ?? "unknown", "reminder:message");
      const reminderMessage = `🔔 Lembrete: ${decrypted}`;
      const previousAttempts = reminder.attempts ?? 0;

      // Resolve recipient using priority chain (Phase 4)
      const recipientContext: RecipientContext = {
        reminderTarget: reminder.target_phone, // From reminder record
        ownerPhone: config.owner_phone, // Fallback to config
        // allowlist could be added from config if needed
      };

      const resolved = resolveRecipient(recipientContext);

      if (!resolved) {
        console.log(`[reminder] No valid recipient for reminder ${reminder.id}`);
        results.push({
          reminder_id: reminder.id,
          success: false,
          error: "No valid recipient could be resolved",
        });
        continue;
      }

      console.log(
        `[reminder] Resolved recipient: ${resolved.phone} (source: ${resolved.source})`
      );

      // Tenta enviar via WhatsApp com retry
      const sendResult = await sendMessageWithRetry(
        config,
        resolved.phone,
        reminderMessage
      );

      const totalAttempts = previousAttempts + sendResult.attempts;

      if (sendResult.success) {
        // Marca como enviado
        await supabase
          .from("shadow_reminders")
          .update({
            sent: true,
            attempts: totalAttempts,
            last_error: null,
            sent_at: new Date().toISOString(),
          })
          .eq("id", reminder.id);

        results.push({
          reminder_id: reminder.id,
          success: true,
          attempts: totalAttempts,
          adapter: sendResult.adapter,
          recipient_source: resolved.source,
          recipient: resolved.phone,
        });
      } else {
        // Registra falha e incrementa tentativas
        const maxTotalAttempts = 9; // 3 execuções x 3 retries cada
        const shouldGiveUp = totalAttempts >= maxTotalAttempts;

        await supabase
          .from("shadow_reminders")
          .update({
            attempts: totalAttempts,
            last_error: sendResult.lastError,
            // Se atingiu máximo de tentativas, marca como "falha permanente"
            ...(shouldGiveUp && { sent: true, failed: true }),
          })
          .eq("id", reminder.id);

        results.push({
          reminder_id: reminder.id,
          success: false,
          error: sendResult.lastError,
          attempts: totalAttempts,
          adapter: sendResult.adapter,
          recipient_source: resolved.source,
          recipient: resolved.phone,
        });

        if (shouldGiveUp) {
          console.log(
            `[reminder] Giving up on reminder ${reminder.id} after ${totalAttempts} total attempts`
          );
        }
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
        adapter_used: adapter.name,
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
