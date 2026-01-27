import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.0";
import {
  handleCorsPreflightRequest,
  corsJsonResponse,
  corsErrorResponse,
} from "../_shared/cors.ts";

interface RequestBody {
  action: "get_config" | "update_config" | "get_metrics" | "get_webhook_logs";
  access_code: string;
  data?: {
    owner_phone?: string | null;
    ignore_groups?: boolean;
    store_relevant_only?: boolean;
    enable_shadow_replies?: boolean;
    evolution_api_url?: string | null;
    evolution_api_key?: string | null;
    evolution_instance_id?: string | null;
    limit?: number;
  };
}

serve(async (req: Request) => {
  const preflight = handleCorsPreflightRequest(req);
  if (preflight) return preflight;

  if (req.method !== "POST") {
    return corsErrorResponse("Method not allowed", 405, req);
  }

  try {
    const body: RequestBody = await req.json();
    if (!body.access_code) {
      return corsErrorResponse("Missing access code", 401, req);
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    const { data: codeData } = await supabase
      .from("access_codes")
      .select("role")
      .eq("code", body.access_code.toUpperCase())
      .eq("is_active", true)
      .single();

    if (!codeData || codeData.role !== "admin") {
      return corsErrorResponse("Admin access required", 403, req);
    }

    if (body.action === "get_config") {
      const config = await getConfig(supabase);
      return corsJsonResponse({ config }, 200, req);
    }

    if (body.action === "update_config") {
      const config = await updateConfig(supabase, body.data ?? {});
      return corsJsonResponse({ config }, 200, req);
    }

    if (body.action === "get_metrics") {
      const metrics = await getMetrics(supabase);
      return corsJsonResponse({ metrics }, 200, req);
    }

    if (body.action === "get_webhook_logs") {
      const limit = Math.max(1, Math.min(200, Number(body.data?.limit ?? 50)));
      const { data } = await supabase
        .from("shadow_webhook_logs")
        .select("*")
        .order("received_at", { ascending: false })
        .limit(limit);
      return corsJsonResponse({ logs: data ?? [] }, 200, req);
    }

    return corsErrorResponse("Invalid action", 400, req);
  } catch (error) {
    return corsErrorResponse(
      error instanceof Error ? error.message : "Internal error",
      500,
      req
    );
  }
});

// deno-lint-ignore no-explicit-any
async function getConfig(supabase: any) {
  const { data } = await supabase.from("shadow_config").select("*").limit(1).maybeSingle();
  if (data) return data;
  const defaults = {
    owner_phone: null,
    ignore_groups: true,
    store_relevant_only: true,
    enable_shadow_replies: true,
    evolution_api_url: null,
    evolution_api_key: null,
    evolution_instance_id: null,
  };
  const { data: created } = await supabase
    .from("shadow_config")
    .insert(defaults)
    .select()
    .single();
  return created ?? defaults;
}

// deno-lint-ignore no-explicit-any
async function updateConfig(supabase: any, updates: Record<string, unknown>) {
  const { data } = await supabase.from("shadow_config").select("id").limit(1).maybeSingle();
  if (!data?.id) {
    await getConfig(supabase);
  }
  const { data: updated, error } = await supabase
    .from("shadow_config")
    .update({ ...updates, updated_at: new Date().toISOString() })
    .eq("id", data?.id)
    .select()
    .single();
  if (error) throw error;
  return updated;
}

// deno-lint-ignore no-explicit-any
async function getMetrics(supabase: any) {
  const contacts = await countTable(supabase, "shadow_contacts");
  const conversations = await countTable(supabase, "shadow_conversations");
  const messages = await countTable(supabase, "shadow_messages");
  const tasksPending = await countTable(supabase, "shadow_tasks", "status", "pending");
  const tasksDone = await countTable(supabase, "shadow_tasks", "status", "done");
  const appointments = await countTable(supabase, "shadow_appointments");

  return {
    contacts,
    conversations,
    messages,
    tasks_pending: tasksPending,
    tasks_done: tasksDone,
    appointments,
  };
}

// deno-lint-ignore no-explicit-any
async function countTable(supabase: any, table: string, field?: string, value?: string) {
  let query = supabase.from(table).select("id", { count: "exact", head: true });
  if (field && value) {
    query = query.eq(field, value);
  }
  const { count } = await query;
  return count ?? 0;
}
