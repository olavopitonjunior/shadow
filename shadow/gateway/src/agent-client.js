export async function callAgent(agentUrl, payload, logger, token) {
  try {
    const headers = { "Content-Type": "application/json" };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    const res = await fetch(agentUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const text = await res.text();
      logger?.warn({ status: res.status, text }, "agent returned non-200");
      return { reply: null, actions: [], error: `agent_status_${res.status}` };
    }
    const data = await res.json();
    return data;
  } catch (err) {
    logger?.error({ err: String(err) }, "agent call failed");
    return { reply: null, actions: [], error: "agent_unreachable" };
  }
}