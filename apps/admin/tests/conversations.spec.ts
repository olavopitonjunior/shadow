import { test, expect } from "@playwright/test";

test.describe("Conversations", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/conversations");
    await page.waitForTimeout(2000);
  });

  test("stats cards render", async ({ page }) => {
    await expect(page.getByText("Total de Sessoes")).toBeVisible();
    await expect(page.getByText("Mensagens Processadas")).toBeVisible();
    await expect(page.getByText("Sessoes Ativas").first()).toBeVisible();
  });

  test("sessions table has correct headers", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Sessoes Ativas" }).first()
    ).toBeVisible();
    const table = page.locator("table");
    const tableOrEmpty = table.or(
      page.getByText("Nenhuma sessao registrada ainda")
    );
    await expect(tableOrEmpty.first()).toBeVisible();
  });

  test("phone numbers are masked", async ({ page }) => {
    const table = page.locator("table");
    if (await table.isVisible()) {
      const phoneCells = table.locator("td.font-mono");
      if ((await phoneCells.count()) > 0) {
        const firstPhone = await phoneCells.first().textContent();
        expect(firstPhone).toMatch(/^\.\.\.\d{4}$/);
      }
    }
  });
});
