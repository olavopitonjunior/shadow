import { test, expect } from "@playwright/test";

const API = "http://localhost:8099";

async function mockAllApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/**`, (route) => {
    const url = route.request().url();
    if (url.includes("/health")) {
      return route.fulfill({ json: { status: "ok", version: "0.3.0" } });
    }
    if (url.includes("/instances")) {
      return route.fulfill({ json: { instances: [] } });
    }
    if (url.includes("/stats/whatsapp")) {
      return route.fulfill({ json: { connections: [] } });
    }
    if (url.includes("/stats/overview")) {
      return route.fulfill({
        json: { users_total: 0, messages_total: 0, tasks_pending: 0, appointments_upcoming: 0 },
      });
    }
    if (url.includes("/config/environment")) {
      return route.fulfill({ json: { variables: {} } });
    }
    if (url.includes("/config/providers")) {
      return route.fulfill({ json: { providers: { anthropic: { configured: false } } } });
    }
    if (url.includes("/config/pricing")) {
      return route.fulfill({ json: { providers: {} } });
    }
    if (url.includes("/logs")) {
      return route.fulfill({ json: { logs: [] } });
    }
    if (url.includes("/proxy/agent")) {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ json: {} });
  });
}

test.describe("Navigation", () => {
  test("sidebar is visible with all navigation links", async ({ page }) => {
    await mockAllApis(page);
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
    await mockAllApis(page);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Shadow Admin" })
    ).toBeVisible();
  });

  test("clicking sidebar links navigates to correct pages", async ({
    page,
  }) => {
    await mockAllApis(page);
    await page.goto("/");

    await page.getByRole("link", { name: "Instancias" }).click();
    await expect(page).toHaveURL(/\/instances/);
    await expect(
      page.getByRole("heading", { name: "Instancias" })
    ).toBeVisible({ timeout: 10000 });

    await page.getByRole("link", { name: "Conversas" }).click();
    await expect(page).toHaveURL(/\/conversations/);
    await page.waitForTimeout(500);

    await page.getByRole("link", { name: "Custos API" }).click();
    await expect(page).toHaveURL(/\/costs/);
    await page.waitForTimeout(500);

    await page.getByRole("link", { name: "Observabilidade" }).click();
    await expect(page).toHaveURL(/\/observability/);
    await page.waitForTimeout(500);

    await page.getByRole("link", { name: "Logs" }).click();
    await expect(page).toHaveURL(/\/logs/);
    await page.waitForTimeout(500);

    await page.getByRole("link", { name: "Configuracoes" }).click();
    await expect(page).toHaveURL(/\/settings/);
    await page.waitForTimeout(500);

    await page.getByRole("link", { name: "Dashboard" }).click();
    await expect(page).toHaveURL("/");
  });

  test("active link is highlighted", async ({ page }) => {
    await mockAllApis(page);
    await page.goto("/instances");
    const activeLink = page.getByRole("link", { name: "Instancias" });
    await expect(activeLink).toHaveClass(/bg-accent/);
  });

  test("header shows page title", async ({ page }) => {
    await mockAllApis(page);
    await page.goto("/costs");
    await expect(
      page.getByRole("heading", { name: "Uso de API & Custos" })
    ).toBeVisible();
  });
});
