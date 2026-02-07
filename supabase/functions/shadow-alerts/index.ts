/**
 * DEPRECATED: This function is being migrated to local scheduler.py
 * See shadow/agent/scheduler.py for the new implementation.
 * Kept for potential Business API integration in SaaS version.
 *
 * This file depends on Evolution/Z-API adapters which have been removed.
 * The local Baileys gateway is now the primary integration.
 *
 * Original description:
 * Shadow Alerts Edge Function - Processa alertas programados e envia via WhatsApp.
 */

import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.39.0";
import {
  handleCorsPreflightRequest,
  corsJsonResponse,
  corsErrorResponse,
} from "../_shared/cors.ts";
import {
  resolveAdapter,
  sendTextWithFallback,
  type ShadowConfig,
} from "../_shared/adapters/index.ts";
import {
  resolveRecipient,
  type RecipientContext,
} from "../_shared/recipient-resolver.ts";
import { encryptText } from "../_shared/crypto.ts";

interface ScheduledAlert {
  id: string;
  owner_id: string;
  alert_time: string;
  timezone: string;
  recurrence: string;
  days_of_week: number[];
  alert_type: string;
  custom_message: string | null;
  include_tasks: boolean;
  include_appointments: boolean;
  include_reminders: boolean;
  include_overdue: boolean;
  is_active: boolean;
  last_sent_at: string | null;
  next_scheduled_at: string | null;
  name: string | null;
}

interface AlertSendResult {
  alert_id: string;
  success: boolean;
  error?: string;
  content?: string;
}

/**
 * Check if current time matches alert time (within 5 minute window)
 */
function shouldSendAlert(alert: ScheduledAlert, now: Date): boolean {
  // Get current time in alert's timezone
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: alert.timezone || 'America/Sao_Paulo',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const currentTime = formatter.format(now);

  // Parse alert time (HH:MM format)
  const alertHour = parseInt(alert.alert_time.split(':')[0]);
  const alertMinute = parseInt(alert.alert_time.split(':')[1]);
  const currentHour = parseInt(currentTime.split(':')[0]);
  const currentMinute = parseInt(currentTime.split(':')[1]);

  // Check if within 5 minute window
  const alertMinutes = alertHour * 60 + alertMinute;
  const currentMinutes = currentHour * 60 + currentMinute;
  const diff = Math.abs(currentMinutes - alertMinutes);

  if (diff > 5 && diff < (24 * 60 - 5)) {
    return false;
  }

  // Check day of week for recurrence
  const dayFormatter = new Intl.DateTimeFormat('en-US', {
    timeZone: alert.timezone || 'America/Sao_Paulo',
    weekday: 'short',
  });
  const dayName = dayFormatter.format(now);
  const dayMap: Record<string, number> = {
    'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6, 'Sun': 7
  };
  const currentDay = dayMap[dayName] || 1;

  if (alert.recurrence === 'daily') {
    return true;
  }

  if (alert.recurrence === 'weekdays') {
    return currentDay >= 1 && currentDay <= 5;
  }

  if (alert.days_of_week && alert.days_of_week.length > 0) {
    return alert.days_of_week.includes(currentDay);
  }

  return true;
}

/**
 * Check if alert was already sent today
 */
function wasAlertSentToday(alert: ScheduledAlert, now: Date): boolean {
  if (!alert.last_sent_at) {
    return false;
  }

  const lastSent = new Date(alert.last_sent_at);
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: alert.timezone || 'America/Sao_Paulo',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });

  const lastSentDate = formatter.format(lastSent);
  const todayDate = formatter.format(now);

  return lastSentDate === todayDate;
}

/**
 * Generate summary content based on user's tasks and appointments
 */
async function generateSummaryContent(
  supabase: SupabaseClient,
  alert: ScheduledAlert,
  userId: string
): Promise<string> {
  const lines: string[] = [];
  const now = new Date();

  // Greeting based on time
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: alert.timezone || 'America/Sao_Paulo',
    hour: '2-digit',
    hour12: false,
  });
  const hour = parseInt(formatter.format(now));

  if (hour < 12) {
    lines.push("☀️ Bom dia!");
  } else if (hour < 18) {
    lines.push("🌤️ Boa tarde!");
  } else {
    lines.push("🌙 Boa noite!");
  }
  lines.push("Aqui está seu resumo:");
  lines.push("");

  const today = new Date().toISOString().split('T')[0];
  let hasContent = false;

  // Get tasks
  if (alert.include_tasks) {
    const { data: tasks } = await supabase
      .from("shadow_tasks")
      .select("id, title, due_at, status")
      .eq("user_id", userId)
      .eq("status", "pending")
      .order("due_at", { ascending: true })
      .limit(10);

    if (tasks && tasks.length > 0) {
      hasContent = true;
      const overdue = tasks.filter(t => t.due_at && t.due_at < today);
      const todayTasks = tasks.filter(t => t.due_at && t.due_at.startsWith(today));
      const future = tasks.filter(t => !t.due_at || (t.due_at > today && !t.due_at.startsWith(today)));

      lines.push(`📋 *TAREFAS* (${tasks.length})`);

      if (alert.include_overdue && overdue.length > 0) {
        lines.push("⚠️ Atrasadas:");
        for (const task of overdue.slice(0, 3)) {
          lines.push(`  • ${task.title}`);
        }
      }

      if (todayTasks.length > 0) {
        lines.push("Hoje:");
        for (const task of todayTasks.slice(0, 5)) {
          lines.push(`  • ${task.title}`);
        }
      } else if (future.length > 0 && overdue.length === 0) {
        lines.push("Pendentes:");
        for (const task of future.slice(0, 5)) {
          lines.push(`  • ${task.title}`);
        }
      }

      lines.push("");
    }
  }

  // Get appointments
  if (alert.include_appointments) {
    const { data: appointments } = await supabase
      .from("shadow_appointments")
      .select("id, title, scheduled_at")
      .eq("user_id", userId)
      .gte("scheduled_at", today)
      .order("scheduled_at", { ascending: true })
      .limit(10);

    // Filter to today's appointments
    const todayAppointments = (appointments || []).filter(a =>
      a.scheduled_at && a.scheduled_at.startsWith(today)
    );

    if (todayAppointments.length > 0) {
      hasContent = true;
      lines.push(`📅 *AGENDA* (${todayAppointments.length})`);

      for (const apt of todayAppointments) {
        const time = apt.scheduled_at.substring(11, 16);
        lines.push(`  • ${time} - ${apt.title}`);
      }

      lines.push("");
    }
  }

  // Closing
  if (hasContent) {
    lines.push("Tenha um ótimo dia! 🚀");
  } else {
    lines.push("Nada programado para hoje! 🎉");
  }

  return lines.join("\n");
}

/**
 * Get alert content based on type
 */
async function getAlertContent(
  supabase: SupabaseClient,
  alert: ScheduledAlert,
  userId: string
): Promise<string> {
  switch (alert.alert_type) {
    case 'summary':
      return await generateSummaryContent(supabase, alert, userId);

    case 'reminder':
    case 'custom':
      return alert.custom_message || "🔔 Alerta programado";

    default:
      return "🔔 Alerta programado";
  }
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

    // Get config
    const { data: configData } = await supabase
      .from("shadow_config")
      .select("*")
      .limit(1)
      .single();

    const config = (configData || {}) as ShadowConfig & { owner_phone?: string };

    // Verify adapter is configured
    const adapter = resolveAdapter(config);
    if (!adapter) {
      return corsJsonResponse(
        { ok: false, error: "No WhatsApp gateway configured" },
        400,
        req
      );
    }

    // Get all active alerts
    const { data: alerts, error } = await supabase
      .from("shadow_scheduled_alerts")
      .select("*")
      .eq("is_active", true);

    if (error) throw error;

    const now = new Date();
    const results: AlertSendResult[] = [];

    for (const alert of (alerts || []) as ScheduledAlert[]) {
      // Check if alert should be sent now
      if (!shouldSendAlert(alert, now)) {
        continue;
      }

      // Check if already sent today
      if (wasAlertSentToday(alert, now)) {
        continue;
      }

      console.log(`[alerts] Processing alert ${alert.id} for ${alert.owner_id}`);

      // Resolve recipient
      const recipientContext: RecipientContext = {
        ownerPhone: alert.owner_id, // owner_id is the phone number
      };

      const resolved = resolveRecipient(recipientContext);
      if (!resolved) {
        console.log(`[alerts] No valid recipient for alert ${alert.id}`);
        results.push({
          alert_id: alert.id,
          success: false,
          error: "No valid recipient",
        });
        continue;
      }

      // Get user_id from shadow_sessions or config
      const { data: sessionData } = await supabase
        .from("shadow_sessions")
        .select("user_id")
        .eq("owner_id", alert.owner_id)
        .limit(1)
        .single();

      const userId = sessionData?.user_id || alert.owner_id;

      // Generate content
      const content = await getAlertContent(supabase, alert, userId);
      const encryptedContent = await encryptText(content ?? "", userId ?? "unknown", "alert:content");

      // Send message
      const sendResult = await sendTextWithFallback(config, resolved.phone, content);

      if (sendResult.success) {
        // Record in history
        await supabase.from("shadow_alert_history").insert({
          alert_id: alert.id,
          owner_id: alert.owner_id,
          content: encryptedContent,
          sent_at: now.toISOString(),
          success: true,
        });

        // Update last_sent_at
        await supabase
          .from("shadow_scheduled_alerts")
          .update({ last_sent_at: now.toISOString() })
          .eq("id", alert.id);

        results.push({
          alert_id: alert.id,
          success: true,
          content: content.substring(0, 100) + "...",
        });

        console.log(`[alerts] Alert ${alert.id} sent successfully`);
      } else {
        // Record failure
        await supabase.from("shadow_alert_history").insert({
          alert_id: alert.id,
          owner_id: alert.owner_id,
          content: encryptedContent,
          sent_at: now.toISOString(),
          success: false,
          error_message: sendResult.error,
        });

        results.push({
          alert_id: alert.id,
          success: false,
          error: sendResult.error,
        });

        console.log(`[alerts] Alert ${alert.id} failed: ${sendResult.error}`);
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
    console.error("[alerts] Error:", error);
    return corsErrorResponse(
      error instanceof Error ? error.message : "Internal error",
      500,
      req
    );
  }
});
