const API_URL = import.meta.env.VITE_ADMIN_API_URL || "http://localhost:8099";
const AGENT_URL = import.meta.env.VITE_AGENT_API_URL || "http://localhost:8090";
const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || "http://localhost:18790";
const API_TOKEN = import.meta.env.VITE_ADMIN_API_TOKEN;

interface FetchOptions extends RequestInit {
  skipAuth?: boolean;
}

async function fetchJson<T>(
  url: string,
  options: FetchOptions = {}
): Promise<T> {
  const { skipAuth, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (!skipAuth && API_TOKEN) {
    headers["Authorization"] = `Bearer ${API_TOKEN}`;
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.text().catch(() => response.statusText);
    throw new Error(`HTTP ${response.status}: ${error}`);
  }

  return response.json();
}

interface Instance {
  id: string;
  name: string;
  phone?: string;
  owner_e164?: string;
  gateway_user_id: string;
  status: string;
  live_status?: string;
  live_phone?: string;
  created_at: string;
  connected_at?: string;
  disconnected_at?: string;
}

interface InstanceStats {
  messages: number;
  sessions: number;
  input_tokens: number;
  output_tokens: number;
  total_cost: number;
}

// Admin API - Sistema de administracao
export const adminApi = {
  // Health check
  getHealth: () => fetchJson<{ status: string; timestamp: string }>(`${API_URL}/health`),

  // Logs
  getLogs: (params?: { level?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.level) query.set("level", params.level);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    return fetchJson<any[]>(`${API_URL}/logs?${query}`);
  },

  // Metrics
  getMetrics: () => fetchJson<any>(`${API_URL}/metrics`),

  // Costs
  getCosts: (params?: { start_date?: string; end_date?: string }) => {
    const query = new URLSearchParams();
    if (params?.start_date) query.set("start_date", params.start_date);
    if (params?.end_date) query.set("end_date", params.end_date);
    return fetchJson<any>(`${API_URL}/costs?${query}`);
  },

  // Stats - Overview
  getStatsOverview: () => fetchJson<{
    users_total: number;
    users_active_24h: number;
    messages_total: number;
    messages_24h: number;
    tasks_pending: number;
    appointments_upcoming: number;
  }>(`${API_URL}/stats/overview`),

  // Stats - Costs
  getStatsCosts: () => fetchJson<{
    input_tokens: number;
    output_tokens: number;
  }>(`${API_URL}/stats/costs`),

  // Stats - Costs Breakdown
  getStatsCostsBreakdown: () => fetchJson<{
    providers: Record<string, {
      input_tokens: number;
      output_tokens: number;
      cost_usd: number;
      calls: number;
      avg_latency_ms: number;
      errors?: number;
      models: Record<string, any>;
    }>;
    total_cost: number;
    days: number;
  }>(`${API_URL}/stats/costs/breakdown`),

  // Stats - Usage History
  getStatsUsageHistory: () => fetchJson<{
    history: Array<{
      day: string;
      provider: string;
      model?: string;
      input_tokens: number;
      output_tokens: number;
      cost: number;
      calls: number;
      avg_latency_ms?: number;
    }>;
  }>(`${API_URL}/stats/usage/history`),

  // Logs - Webhook Logs
  getWebhookLogs: (params?: {
    source?: string;
    direction?: string;
    search?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.source) query.set("source", params.source);
    if (params?.direction) query.set("direction", params.direction);
    if (params?.search) query.set("search", params.search);
    if (params?.date_from) query.set("date_from", params.date_from);
    if (params?.date_to) query.set("date_to", params.date_to);
    if (params?.limit) query.set("limit", String(params.limit));
    return fetchJson<{
      logs: Array<{
        id: string;
        source: string;
        user_phone?: string;
        contact_phone?: string;
        direction: string;
        content_type?: string;
        is_group?: boolean;
        received_at: string;
      }>;
      source?: string;
    }>(`${API_URL}/logs/webhooks?${query}`);
  },

  // Logs - Error Logs
  getErrorLogs: (limit?: number) => {
    const query = new URLSearchParams();
    if (limit) query.set("limit", String(limit));
    return fetchJson<{
      errors: any[];
      note?: string;
    }>(`${API_URL}/logs/errors?${query}`);
  },

  // Stats - WhatsApp
  getStatsWhatsApp: () => fetchJson<{
    connections: Array<{
      provider: string;
      instance_id: string;
      status: string;
      details: any;
      checked_at: string;
    }>;
  }>(`${API_URL}/stats/whatsapp`),

  // Proxy - Agent Status
  getProxyAgentStatus: () => fetchJson<{
    status: string;
    components: {
      storage: string;
      sessions: string;
      rate_limiter: string;
      scheduler: string;
    };
    sessions: {
      total_sessions: number;
      active_sessions: number;
      total_messages: number;
      total_input_tokens: number;
      total_output_tokens: number;
    };
    scheduler: any;
  }>(`${API_URL}/proxy/agent/status`),

  // Config - Pricing
  getConfigPricing: () => fetchJson<{
    pricing: Array<{
      provider: string;
      model: string;
      input_price_per_mtok: number;
      output_price_per_mtok: number;
    }>;
  }>(`${API_URL}/config/pricing`),

  // Config - Environment Variables
  getConfigEnvironment: () => fetchJson<{
    variables: Record<string, { configured: boolean; masked_value?: string }>;
  }>(`${API_URL}/config/environment`),

  // Config - Providers
  getConfigProviders: () => fetchJson<{
    providers: Record<string, {
      configured: boolean;
      models: string[];
    }>;
  }>(`${API_URL}/config/providers`),

  // Instances
  getInstances: () => fetchJson<{ instances: Instance[] }>(`${API_URL}/instances`),
  createInstance: (name: string) => fetchJson<Instance & { qr?: string }>(`${API_URL}/instances`, {
    method: "POST",
    body: JSON.stringify({ name }),
  }),
  deleteInstance: (id: string) => fetchJson<{ status: string }>(`${API_URL}/instances/${id}`, {
    method: "DELETE",
  }),
  connectInstance: (id: string) => fetchJson<{ id: string; status: string; qr?: string }>(`${API_URL}/instances/${id}/connect`, {
    method: "POST",
  }),
  disconnectInstance: (id: string) => fetchJson<{ id: string; status: string }>(`${API_URL}/instances/${id}/disconnect`, {
    method: "POST",
  }),
  getInstanceQR: (id: string) => fetchJson<{ qr: string | null; status: string }>(`${API_URL}/instances/${id}/qr`),
  getInstanceStatus: (id: string) => fetchJson<{ status: string; phone?: string; qr?: string }>(`${API_URL}/instances/${id}/status`),
  getInstanceStats: (id: string) => fetchJson<InstanceStats>(`${API_URL}/instances/${id}/stats`),
  getInstanceDetail: (id: string) => fetchJson<Instance>(`${API_URL}/instances/${id}`),
  getInstanceConversations: (id: string) => fetchJson<{ conversations: any[] }>(`${API_URL}/instances/${id}/conversations`),
  getInstanceCosts: (id: string) => fetchJson<{ providers: Record<string, any>; total_cost: number; days: number }>(`${API_URL}/instances/${id}/costs`),
  getInstanceLogs: (id: string) => fetchJson<{ logs: any[] }>(`${API_URL}/instances/${id}/logs`),
};

// Agent API - Shadow agent endpoints
export const agentApi = {
  // Health check
  getHealth: () => fetchJson<{ status: string }>(`${AGENT_URL}/health`, { skipAuth: true }),

  // Sessions
  getSessions: () => fetchJson<any[]>(`${AGENT_URL}/sessions`),
  getSession: (sessionId: string) => fetchJson<any>(`${AGENT_URL}/sessions/${sessionId}`),

  // Tasks
  getTasks: (params?: { owner_id?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.owner_id) query.set("owner_id", params.owner_id);
    if (params?.limit) query.set("limit", String(params.limit));
    return fetchJson<any[]>(`${AGENT_URL}/tasks?${query}`);
  },

  // Appointments
  getAppointments: (params?: { owner_id?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.owner_id) query.set("owner_id", params.owner_id);
    if (params?.limit) query.set("limit", String(params.limit));
    return fetchJson<any[]>(`${AGENT_URL}/appointments?${query}`);
  },

  // Contacts
  getContacts: (params?: { owner_id?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.owner_id) query.set("owner_id", params.owner_id);
    if (params?.limit) query.set("limit", String(params.limit));
    return fetchJson<any[]>(`${AGENT_URL}/contacts?${query}`);
  },

  // Conversations
  getConversations: (params?: { limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    return fetchJson<any[]>(`${AGENT_URL}/conversations?${query}`);
  },
};

// Gateway API - Baileys WhatsApp gateway
export const gatewayApi = {
  // Status
  getStatus: () => fetchJson<{ connected: boolean; user?: any }>(`${GATEWAY_URL}/status`, { skipAuth: true }),

  // Send message
  sendMessage: (to: string, message: string) =>
    fetchJson(`${GATEWAY_URL}/send`, {
      method: "POST",
      body: JSON.stringify({ to, message }),
    }),

  // QR Code (for authentication)
  getQR: () => fetchJson<{ qr?: string; authenticated: boolean }>(`${GATEWAY_URL}/qr`, { skipAuth: true }),

  // Disconnect
  disconnect: () =>
    fetchJson(`${GATEWAY_URL}/disconnect`, {
      method: "POST",
    }),
};

// Re-export for convenience
export { API_URL, AGENT_URL, GATEWAY_URL };
