import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("sidebar is visible with all navigation links", async ({ page }) => {
    await page.goto("/");
    const sidebar = page.locator("aside");
    await expect(sidebar).toBeVisible();

    const navItems = [
      "Dashboard",
      "Instancias",
      "Conversas",
      "Custos API",
      "Observabilidade",
      "Logs",
      "Configuracoes",
    ];
    for (const label of navItems) {
      await expect(sidebar.getByRole("link", { name: label })).toBeVisible();
    }
  });

  test("brand title is visible", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Shadow Admin" })
    ).toBeVisible();
  });

  test("clicking sidebar links navigates to correct pages", async ({
    page,
  }) => {
    await page.goto("/");

    await page.getByRole("link", { name: "Instancias" }).click();
    await expect(page).toHaveURL(/\/instances/);
    await expect(
      page.getByRole("heading", { name: "Instancias" })
    ).toBeVisible();

    await page.getByRole("link", { name: "Conversas" }).click();
    await expect(page).toHaveURL(/\/conversations/);

    await page.getByRole("link", { name: "Custos API" }).click();
    await expect(page).toHaveURL(/\/costs/);

    await page.getByRole("link", { name: "Observabilidade" }).click();
    await expect(page).toHaveURL(/\/observability/);

    await page.getByRole("link", { name: "Logs" }).click();
    await expect(page).toHaveURL(/\/logs/);

    await page.getByRole("link", { name: "Configuracoes" }).click();
    await expect(page).toHaveURL(/\/settings/);

    await page.getByRole("link", { name: "Dashboard" }).click();
    await expect(page).toHaveURL("/");
  });

  test("active link is highlighted", async ({ page }) => {
    await page.goto("/instances");
    const activeLink = page.getByRole("link", { name: "Instancias" });
    await expect(activeLink).toHaveClass(/bg-accent/);
  });

  test("header shows page title", async ({ page }) => {
    await page.goto("/costs");
    await expect(
      page.getByRole("heading", { name: "Uso de API & Custos" })
    ).toBeVisible();
  });
});
