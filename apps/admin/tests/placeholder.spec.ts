import { test, expect } from "@playwright/test";

test.describe("Observability", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/observability");
    await page.waitForTimeout(2000);
  });

  test("health check cards render", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Observabilidade" })
    ).toBeVisible();

    // Health check section heading
    await expect(page.getByText("Health Checks")).toBeVisible();

    // All four health check cards
    await expect(page.getByText("Gateway (Baileys)")).toBeVisible();
    await expect(page.getByText("Agent API")).toBeVisible();
    await expect(page.getByText("Admin API")).toBeVisible();
    await expect(page.getByText("Database")).toBeVisible();

    // Check for "Tempo de Resposta" label (in health check cards)
    await expect(page.getByText("Tempo de Resposta").first()).toBeVisible();
  });

  test("performance metrics section visible", async ({ page }) => {
    await expect(page.getByText("Metricas de Performance")).toBeVisible();

    // Three metric cards
    await expect(page.getByText("Latencia Media")).toBeVisible();
    await expect(page.getByText("Taxa de Erro")).toBeVisible();
    await expect(page.getByText("Uptime Estimado")).toBeVisible();
  });

  test("instances table section visible", async ({ page }) => {
    await expect(page.getByText("Instancias WhatsApp")).toBeVisible();

    // Table headers should be present (or loading skeleton)
    const tableHeaders = page.getByRole("columnheader", { name: "Nome" });
    const skeleton = page.locator("[class*='skeleton']").first();

    await expect(tableHeaders.or(skeleton)).toBeVisible();
  });
});

test.describe("Logs", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/logs");
    await page.waitForTimeout(2000);
  });

  test("tab buttons are visible and clickable", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Logs" })).toBeVisible();

    // All three tabs
    const webhookTab = page.getByRole("button", { name: "Webhook" });
    const applicationTab = page.getByRole("button", { name: "Aplicacao" });
    const errorsTab = page.getByRole("button", { name: "Erros" });

    await expect(webhookTab).toBeVisible();
    await expect(applicationTab).toBeVisible();
    await expect(errorsTab).toBeVisible();

    // Click application tab
    await applicationTab.click();
    await expect(page.getByText("Historico de Uso da API")).toBeVisible();

    // Click errors tab
    await errorsTab.click();
    await expect(page.getByText("Logs de Erro")).toBeVisible();
  });

  test("webhook tab shows filters section", async ({ page }) => {
    // Webhook tab should be active by default
    await expect(page.getByText("Filtros")).toBeVisible();

    // Filter controls
    await expect(page.getByText("Instancia")).toBeVisible();
    await expect(page.getByText("Direcao")).toBeVisible();
    await expect(page.getByText("Buscar Telefone")).toBeVisible();
    await expect(page.getByText("Data Inicial")).toBeVisible();
    await expect(page.getByText("Data Final")).toBeVisible();

    // Clear filters button
    await expect(
      page.getByRole("button", { name: "Limpar Filtros" })
    ).toBeVisible();
  });

  test("bottom stats cards visible", async ({ page }) => {
    // Stats cards at bottom
    await expect(page.getByText("Total de Logs")).toBeVisible();
    await expect(page.getByText("Erros")).toBeVisible();
    await expect(page.getByText("Warnings")).toBeVisible();
  });
});

test.describe("Settings", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings");
    await page.waitForTimeout(2000);
  });

  test("page heading and env vars section visible", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Configuracoes" })
    ).toBeVisible();

    await expect(page.getByText("Variaveis de Ambiente")).toBeVisible();

    // Should have env var cards (or skeletons while loading)
    const skeleton = page.locator("[class*='skeleton']").first();
    const envContent = page.getByText("Nao configurado");

    await expect(skeleton.or(envContent)).toBeVisible({ timeout: 5000 });
  });

  test("provider status cards visible", async ({ page }) => {
    await expect(page.getByText("Status dos Providers")).toBeVisible();

    // Provider names should appear (or skeletons)
    const anthropicProvider = page.getByText("anthropic");
    const googleProvider = page.getByText("google");
    const openaiProvider = page.getByText("openai");
    const skeleton = page.locator("[class*='skeleton']").first();

    // At least one provider should be visible or skeleton should be present
    await expect(
      anthropicProvider.or(googleProvider).or(openaiProvider).or(skeleton)
    ).toBeVisible({ timeout: 5000 });
  });

  test("service connections visible", async ({ page }) => {
    await expect(page.getByText("Conexoes de Servico")).toBeVisible();

    // Service connection cards
    await expect(page.getByText("Gateway (Baileys)")).toBeVisible();
    await expect(page.getByText("Agent API")).toBeVisible();
    await expect(page.getByText("Admin API")).toBeVisible();
  });
});
