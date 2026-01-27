import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.0";
import {
  handleCorsPreflightRequest,
  corsJsonResponse,
  corsErrorResponse,
} from "../_shared/cors.ts";

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

    const nowIso = new Date().toISOString();
    const { data: reminders, error } = await supabase
      .from("shadow_reminders")
      .select("*")
      .eq("sent", false)
      .lte("remind_at", nowIso)
      .limit(50);

    if (error) throw error;

    const processed: string[] = [];
    for (const reminder of reminders ?? []) {
      // TODO: send message to WhatsApp gateway if configured
      await supabase
        .from("shadow_reminders")
        .update({ sent: true })
        .eq("id", reminder.id);
      processed.push(reminder.id);
    }

    return corsJsonResponse(
      { ok: true, processed_count: processed.length, processed },
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
