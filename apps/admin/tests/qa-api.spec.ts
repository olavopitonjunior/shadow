/**
 * QA Tests: API Endpoint Validation
 *
 * Tests admin API and gateway endpoints directly using fetch().
 * Requires all 3 services running: Admin API (:8099), Gateway (:18790), Frontend (:5173).
 */
import { test, expect } from "@playwright/test";

const ADMIN = "http://localhost:8099";
const GATEWAY = "http://localhost:18790";

let createdInstanceId: string | null = null;

test.describe("API: Health & Config", () => {
  test("A1: GET /health retorna status ok", async ({ request }) => {
    const res = await request.get(`${ADMIN}/health`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(body.version).toBeTruthy();
    expect(body.time).toBeTruthy();
  });

  test("A21: GET /config/environment retorna variables", async ({ request }) => {
    const res = await request.get(`${ADMIN}/config/environment`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.variables).toBeTruthy();
    expect(body.variables.SUPABASE_URL).toHaveProperty("configured");
  });

  test("A22: GET /config/providers retorna providers", async ({ request }) => {
    const res = await request.get(`${ADMIN}/config/providers`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.providers).toBeTruthy();
    expect(body.providers).toHaveProperty("anthropic");
    expect(body.providers).toHaveProperty("google");
  });
});

test.describe("API: Stats & Overview", () => {
  test("A15: GET /stats/overview retorna dados", async ({ request }) => {
    const res = await request.get(`${ADMIN}/stats/overview`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(typeof body.users_total).toBe("number");
    expect(typeof body.messages_total).toBe("number");
  });

  test("A16: GET /stats/whatsapp retorna connections", async ({ request }) => {
    const res = await request.get(`${ADMIN}/stats/whatsapp`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.connections).toBeInstanceOf(Array);
  });

  test("A17: GET /stats/usage/history retorna history", async ({ request }) => {
    const res = await request.get(`${ADMIN}/stats/usage/history`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("history");
  });

  test("A18: GET /stats/costs/breakdown retorna breakdown", async ({ request }) => {
    const res = await request.get(`${ADMIN}/stats/costs/breakdown`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("providers");
    expect(typeof body.total_cost).toBe("number");
  });
});

test.describe("API: Proxy", () => {
  test("A19: GET /proxy/agent/status (pode falhar se agent down)", async ({ request }) => {
    const res = await request.get(`${ADMIN}/proxy/agent/status`);
    // Accept both 200 (agent up) and 200 with error field (agent down)
    expect(res.status()).toBe(200);
  });

  test("A20: GET /proxy/gateway/status retorna status", async ({ request }) => {
    const res = await request.get(`${ADMIN}/proxy/gateway/status`);
    expect(res.status()).toBe(200);
  });
});

test.describe("API: Logs", () => {
  test("A23: GET /logs/webhooks retorna array", async ({ request }) => {
    const res = await request.get(`${ADMIN}/logs/webhooks`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("logs");
  });

  test("A24: GET /logs/errors retorna errors array", async ({ request }) => {
    const res = await request.get(`${ADMIN}/logs/errors`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.errors).toBeInstanceOf(Array);
  });

  test("A25: GET /logs?limit=10 retorna logs array", async ({ request }) => {
    const res = await request.get(`${ADMIN}/logs?limit=10`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("logs");
  });
});

test.describe("API: Instance CRUD lifecycle", () => {
  test("A2: GET /instances retorna array", async ({ request }) => {
    const res = await request.get(`${ADMIN}/instances`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.instances).toBeInstanceOf(Array);
  });

  test("A3: POST /instances cria nova instancia", async ({ request }) => {
    const res = await request.post(`${ADMIN}/instances`, {
      data: { name: "QA Test Instance" },
    });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.id).toBeTruthy();
    expect(body.name).toBe("QA Test Instance");
    expect(body.gateway_user_id).toBeTruthy();
    expect(["connecting", "qr_pending", "disconnected"]).toContain(body.status);
    createdInstanceId = body.id;
  });

  test("A4: GET /instances/{id} retorna detalhes", async ({ request }) => {
    // Use existing or created instance
    const listRes = await request.get(`${ADMIN}/instances`);
    const instances = (await listRes.json()).instances;
    if (instances.length === 0) {
      test.skip();
      return;
    }
    const id = instances[0].id;

    const res = await request.get(`${ADMIN}/instances/${id}`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.id).toBe(id);
    expect(body).toHaveProperty("live_status");
  });

  test("A5: GET /instances/{id}/status retorna status", async ({ request }) => {
    const listRes = await request.get(`${ADMIN}/instances`);
    const instances = (await listRes.json()).instances;
    if (instances.length === 0) {
      test.skip();
      return;
    }
    const id = instances[0].id;

    const res = await request.get(`${ADMIN}/instances/${id}/status`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("status");
  });

  test("A6: GET /instances/{id}/qr retorna qr", async ({ request }) => {
    const listRes = await request.get(`${ADMIN}/instances`);
    const instances = (await listRes.json()).instances;
    if (instances.length === 0) {
      test.skip();
      return;
    }
    const id = instances[0].id;

    const res = await request.get(`${ADMIN}/instances/${id}/qr`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("status");
  });

  test("A7: GET /instances/{id}/stats retorna metricas", async ({ request }) => {
    const listRes = await request.get(`${ADMIN}/instances`);
    const instances = (await listRes.json()).instances;
    if (instances.length === 0) {
      test.skip();
      return;
    }
    const id = instances[0].id;

    const res = await request.get(`${ADMIN}/instances/${id}/stats`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(typeof body.messages).toBe("number");
    expect(typeof body.sessions).toBe("number");
    expect(typeof body.input_tokens).toBe("number");
    expect(typeof body.output_tokens).toBe("number");
  });

  test("A8: GET /instances/{id}/conversations retorna array", async ({ request }) => {
    const listRes = await request.get(`${ADMIN}/instances`);
    const instances = (await listRes.json()).instances;
    if (instances.length === 0) {
      test.skip();
      return;
    }
    const id = instances[0].id;

    const res = await request.get(`${ADMIN}/instances/${id}/conversations`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("conversations");
  });

  test("A9: GET /instances/{id}/costs retorna breakdown", async ({ request }) => {
    const listRes = await request.get(`${ADMIN}/instances`);
    const instances = (await listRes.json()).instances;
    if (instances.length === 0) {
      test.skip();
      return;
    }
    const id = instances[0].id;

    const res = await request.get(`${ADMIN}/instances/${id}/costs`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("providers");
    expect(typeof body.total_cost).toBe("number");
  });

  test("A10: GET /instances/{id}/logs retorna array", async ({ request }) => {
    const listRes = await request.get(`${ADMIN}/instances`);
    const instances = (await listRes.json()).instances;
    if (instances.length === 0) {
      test.skip();
      return;
    }
    const id = instances[0].id;

    const res = await request.get(`${ADMIN}/instances/${id}/logs`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("logs");
  });

  test("A14: GET /instances/nonexistent/status retorna 404", async ({ request }) => {
    const res = await request.get(`${ADMIN}/instances/nonexistent-id-000/status`);
    expect(res.status()).toBe(404);
  });
});

test.describe("API: Instance Actions (connect/disconnect/delete)", () => {
  let testInstanceId: string;

  test.beforeAll(async ({ request }) => {
    // Create a dedicated test instance for actions
    const res = await request.post(`${ADMIN}/instances`, {
      data: { name: "QA Action Test" },
    });
    const body = await res.json();
    testInstanceId = body.id;
  });

  test("A11: POST /instances/{id}/connect retorna status e qr", async ({ request }) => {
    if (!testInstanceId) test.skip();
    const res = await request.post(`${ADMIN}/instances/${testInstanceId}/connect`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.id).toBe(testInstanceId);
    expect(body).toHaveProperty("status");
  });

  test("A12: POST /instances/{id}/disconnect retorna disconnected", async ({ request }) => {
    if (!testInstanceId) test.skip();
    const res = await request.post(`${ADMIN}/instances/${testInstanceId}/disconnect`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("disconnected");
  });

  test("A13: DELETE /instances/{id} remove instancia", async ({ request }) => {
    if (!testInstanceId) test.skip();
    const res = await request.delete(`${ADMIN}/instances/${testInstanceId}`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("deleted");

    // Confirm it's gone
    const check = await request.get(`${ADMIN}/instances/${testInstanceId}`);
    expect(check.status()).toBe(404);
  });
});

test.describe("API: Gateway Direct", () => {
  test("A26: GET /sessions retorna sessions", async ({ request }) => {
    const res = await request.get(`${GATEWAY}/sessions`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.sessions).toBeInstanceOf(Array);
  });

  test("A27: GET /status retorna legacy status", async ({ request }) => {
    const res = await request.get(`${GATEWAY}/status`);
    expect(res.status()).toBe(200);
  });
});
