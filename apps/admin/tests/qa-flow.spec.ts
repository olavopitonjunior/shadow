/**
 * QA Tests: Real Flow (requires running services)
 *
 * Tests that interact with the real API through the browser.
 * Requires: Admin API (:8099), Gateway (:18790), Frontend (:5173).
 */
import { test, expect } from "@playwright/test";

test.describe("Flow: Instance lifecycle via browser", () => {
  let createdInstanceId: string | null = null;

  test("F1: Criar instancia pelo dialog e ver na lista", async ({ page }) => {
    await page.goto("/instances");
    await page.waitForTimeout(2000);

    // Open dialog
    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await expect(page.locator("[role='dialog']")).toBeVisible();

    // Fill name
    const input = page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...");
    await input.fill("QA Flow Test");
    await page.locator("[role='dialog']").getByRole("button", { name: "Criar" }).click();

    // Should advance to QR step (real API call)
    await expect(
      page.getByRole("heading", { name: "Conectar WhatsApp" })
    ).toBeVisible({ timeout: 10000 });

    // Close dialog (don't wait for scan)
    await page.keyboard.press("Escape");

    // Instance should appear in list
    await page.waitForTimeout(2000);
    await expect(page.getByText("QA Flow Test").first()).toBeVisible({ timeout: 5000 });

    // Capture id from the card link
    const cardLink = page.locator("a[href*='/instances/']").first();
    if (await cardLink.isVisible()) {
      const href = await cardLink.getAttribute("href");
      createdInstanceId = href?.split("/instances/")[1] || null;
    }
  });

  test("F2: Ver detalhes de instancia existente", async ({ page }) => {
    await page.goto("/instances");
    await page.waitForTimeout(2000);

    // Find a card with "Ver detalhes"
    const detailButton = page.getByRole("button", { name: "Ver detalhes" }).first();
    if (!(await detailButton.isVisible())) {
      test.skip();
      return;
    }

    await detailButton.click();
    await expect(page).toHaveURL(/\/instances\/.+/);

    // Verify tabs exist
    await expect(page.getByRole("tab", { name: /Geral/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Conversas/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Custos/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Logs/ })).toBeVisible();

    // Verify stat cards
    await expect(page.getByText("Mensagens")).toBeVisible();
  });

  test("F3: Tabs de detalhe carregam dados", async ({ page }) => {
    await page.goto("/instances");
    await page.waitForTimeout(2000);

    const detailButton = page.getByRole("button", { name: "Ver detalhes" }).first();
    if (!(await detailButton.isVisible())) {
      test.skip();
      return;
    }
    await detailButton.click();
    await page.waitForTimeout(1000);

    // Tab Conversas
    await page.getByRole("tab", { name: /Conversas/ }).click();
    await page.waitForTimeout(1000);
    // Should show table or "Nenhuma conversa registrada"
    const convContent = page.getByText("Nenhuma conversa registrada").or(
      page.locator("table")
    );
    await expect(convContent).toBeVisible({ timeout: 5000 });

    // Tab Custos
    await page.getByRole("tab", { name: /Custos/ }).click();
    await page.waitForTimeout(1000);
    await expect(page.getByText(/Custo Total/)).toBeVisible({ timeout: 5000 });

    // Tab Logs
    await page.getByRole("tab", { name: /Logs/ }).click();
    await page.waitForTimeout(1000);
    const logContent = page.getByText("Nenhum log registrado").or(
      page.locator("table")
    );
    await expect(logContent).toBeVisible({ timeout: 5000 });
  });

  test("F4: Dashboard mostra WhatsApp connections", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(3000);
    await expect(
      page.getByRole("heading", { name: "WhatsApp Connections" })
    ).toBeVisible();
  });

  test("F5: Todas as paginas carregam sem crash", async ({ page }) => {
    const pages = [
      { url: "/", heading: "Dashboard" },
      { url: "/instances", heading: "Instancias" },
      { url: "/conversations", heading: "Conversas" },
      { url: "/costs", heading: "Uso de API" },
      { url: "/observability", heading: "Observabilidade" },
      { url: "/logs", heading: "Logs" },
      { url: "/settings", heading: "Configuracoes" },
    ];

    for (const p of pages) {
      await page.goto(p.url);
      await page.waitForTimeout(1500);
      // At minimum the page should not show a React error boundary
      const errorBoundary = page.getByText("Something went wrong");
      expect(await errorBoundary.isVisible()).toBe(false);
    }
  });

  test("F6: Deletar instancia de teste (cleanup)", async ({ page }) => {
    await page.goto("/instances");
    await page.waitForTimeout(2000);

    // Find "QA Flow Test" or "QA Action Test" instances to clean up
    const cards = page.locator("text=QA");
    const count = await cards.count();
    if (count === 0) {
      test.skip();
      return;
    }

    // Delete via dropdown
    const dropdowns = page.locator("button:has(svg.lucide-more-vertical)");
    const dropdownCount = await dropdowns.count();
    if (dropdownCount > 0) {
      await dropdowns.last().click();
      const removeBtn = page.getByRole("menuitem", { name: "Remover" });
      if (await removeBtn.isVisible()) {
        await removeBtn.click();
        await page.waitForTimeout(2000);
      }
    }
  });
});
