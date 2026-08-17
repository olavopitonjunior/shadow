import { test, expect } from "@playwright/test";

const API = "http://localhost:8099";

async function mockAllApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/**`, (route) => {
    const url = route.request().url();
    if (url.includes("/health")) {
      return route.fulfill({ json: { status: "ok", version: "0.3.0", time: new Date().toISOString() } });
    }
    if (url.includes("/instances")) {
      return route.fulfill({ json: { instances: [] } });
    }
    if (url.includes("/stats/whatsapp")) {
      return route.fulfill({ json: { connections: [{ provider: "baileys", status: "connected" }] } });
    }
    if (url.includes("/stats/overview")) {
      return route.fulfill({
        json: { users_total: 10, messages_total: 200, tasks_pending: 1, appointments_upcoming: 0 },
      });
    }
    if (url.includes("/stats/costs/breakdown")) {
      return route.fulfill({
        json: { providers: { anthropic: { cost_usd: 0.05, calls: 20 } }, total_cost: 0.05 },
      });
    }
    if (url.includes("/stats/usage/history")) {
      return route.fulfill({ json: { history: [] } });
    }
    if (url.includes("/config/environment")) {
      return route.fulfill({
        json: {
          variables: {
            SUPABASE_URL: { configured: false, value: "" },
            ANTHROPIC_API_KEY: { configured: true, value: "sk-***" },
          },
        },
      });
    }
    if (url.includes("/config/providers")) {
      return route.fulfill({
        json: {
          providers: {
            anthropic: { configured: true, model: "claude-sonnet-4-5-20250929" },
            google: { configured: false },
            openai: { configured: false },
          },
        },
      });
    }
    if (url.includes("/config/pricing")) {
      return route.fulfill({ json: { providers: {} } });
    }
    if (url.includes("/logs/webhooks")) {
      return route.fulfill({ json: { logs: [] } });
    }
    if (url.includes("/logs/errors")) {
      return route.fulfill({ json: { errors: [], note: "Error log collection not yet implemented" } });
    }
    if (url.includes("/logs")) {
      return route.fulfill({ json: { logs: [] } });
    }
    if (url.includes("/proxy/agent")) {
      return route.fulfill({ json: { status: "ok" } });
    }
    if (url.includes("/proxy/gateway")) {
      return route.fulfill({ json: { status: "ok" } });
    }
    return route.fulfill({ json: {} });
  });
}

test.describe("Observability", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
    await page.goto("/observability");
  });

  test("health check cards render", async ({ page }) => {
    await expect(page.getByText("Health Checks")).toBeVisible({ timeout: 5000 });
    // At least one health card should be visible
    const card = page.getByText("Gateway (Baileys)")
      .or(page.getByText("Agent API"))
      .or(page.getByText("Admin API"));
    await expect(card.first()).toBeVisible({ timeout: 5000 });
  });

  test("performance metrics section visible", async ({ page }) => {
    await expect(page.getByText("Metricas de Performance")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Latencia Media")).toBeVisible();
    await expect(page.getByText("Taxa de Erro")).toBeVisible();
    await expect(page.getByText("Uptime Estimado")).toBeVisible();
  });

  test("instances table section visible", async ({ page }) => {
    await expect(page.getByText("Instancias WhatsApp")).toBeVisible({ timeout: 5000 });
    // Table or empty state
    const table = page.locator("table");
    const emptyState = page.getByText("Nenhuma instancia encontrada");
    await expect(table.or(emptyState)).toBeVisible({ timeout: 5000 });
  });
});

test.describe("Logs", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
    await page.goto("/logs");
  });

  test("tab buttons are visible and clickable", async ({ page }) => {
    const webhookTab = page.getByRole("button", { name: "Webhook" });
    const applicationTab = page.getByRole("button", { name: "Aplicacao" });
    const errorsTab = page.getByRole("button", { name: "Erros" });

    await expect(webhookTab).toBeVisible({ timeout: 5000 });
    await expect(applicationTab).toBeVisible();
    await expect(errorsTab).toBeVisible();

    // Click application tab and verify content
    await applicationTab.click();
    await page.waitForTimeout(500);
    await expect(page.getByText("Historico de Uso da API")).toBeVisible({ timeout: 5000 });

    // Click errors tab
    await errorsTab.click();
    await page.waitForTimeout(500);
    await expect(page.getByText("Logs de Erro")).toBeVisible({ timeout: 5000 });
  });

  test("webhook tab shows filters section", async ({ page }) => {
    await expect(page.getByText("Filtros").first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Instancia").first()).toBeVisible();
    await expect(page.getByText("Direcao").first()).toBeVisible();
    await expect(page.getByText("Buscar Telefone")).toBeVisible();
    await expect(page.getByText("Data Inicial")).toBeVisible();
    await expect(page.getByText("Data Final")).toBeVisible();
    await expect(page.getByRole("button", { name: "Limpar Filtros" })).toBeVisible();
  });

  test("bottom stats cards visible", async ({ page }) => {
    await expect(page.getByText("Total de Logs")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("h3, [class*='CardTitle']").filter({ hasText: /^Erros$/ })).toBeVisible();
    await expect(page.getByText("Warnings")).toBeVisible();
  });
});

test.describe("Settings", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
    await page.goto("/settings");
  });

  test("page heading and env vars section visible", async ({ page }) => {
    await expect(page.getByText("Variaveis de Ambiente")).toBeVisible({ timeout: 5000 });
  });

  test("provider status cards visible", async ({ page }) => {
    await expect(page.getByText("Status dos Providers")).toBeVisible({ timeout: 5000 });
    const provider = page.getByText("anthropic")
      .or(page.getByText("google"))
      .or(page.getByText("openai"));
    await expect(provider.first()).toBeVisible({ timeout: 5000 });
  });

  test("service connections visible", async ({ page }) => {
    await expect(page.getByText("Conexoes de Servico")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Gateway (Baileys)").last()).toBeVisible();
    await expect(page.getByText("Agent API").last()).toBeVisible();
    await expect(page.getByText("Admin API")).toBeVisible();
  });
});
