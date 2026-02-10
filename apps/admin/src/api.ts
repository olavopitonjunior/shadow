const API_URL = import.meta.env.VITE_ADMIN_API_URL || "http://localhost:8099";
const API_TOKEN = import.meta.env.VITE_ADMIN_API_TOKEN;

async function getJson<T>(path: string): Promise<T> {
  const headers: HeadersInit = {};
  if (API_TOKEN) {
    headers["Authorization"] = `Bearer ${API_TOKEN}`;
  }
  const res = await fetch(`${API_URL}${path}`, { headers });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return await res.json();
}

export const api = {
  overview: () => getJson<any>("/stats/overview"),
  integrations: () => getJson<any>("/stats/integrations"),
  whatsapp: () => getJson<any>("/stats/whatsapp"),
  costs: () => getJson<any>("/stats/costs"),
  tables: () => getJson<any>("/stats/tables"),
  webhookLogs: (params?: { source?: string; direction?: string; date_from?: string; date_to?: string; search?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.source) query.set("source", params.source);
    if (params?.direction) query.set("direction", params.direction);
    if (params?.date_from) query.set("date_from", params.date_from);
    if (params?.date_to) query.set("date_to", params.date_to);
    if (params?.search) query.set("search", params.search);
    if (params?.limit) query.set("limit", String(params.limit));
    const queryString = query.toString();
    return getJson<any>(`/logs/webhooks${queryString ? `?${queryString}` : ""}`);
  },
  users: () => getJson<any>("/users"),
  agentStatus: () => getJson<any>("/proxy/agent/status"),
  agentSessions: () => getJson<any>("/proxy/agent/sessions"),
  agentSession: (id: string) => getJson<any>(`/proxy/agent/sessions/${id}`),
  auditSummary: () => getJson<any>("/proxy/agent/audit/summary"),
  gatewayStatus: () => getJson<any>("/proxy/gateway/status"),
  gatewayGroups: () => getJson<any>("/proxy/gateway/groups"),
  environment: () => getJson<any>("/config/environment"),
  providers: () => getJson<any>("/config/providers"),
  pricing: () => getJson<any>("/config/pricing"),
};
