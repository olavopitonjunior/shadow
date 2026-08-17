import { test, expect } from "@playwright/test";

const API = "http://localhost:8099";

async function mockInstanceApis(
  page: import("@playwright/test").Page,
  instances: any[] = []
) {
  await page.route(`${API}/instances`, (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: { instances } });
    }
    return route.fulfill({
      json: {
        id: "new-inst",
        name: "Test",
        gateway_user_id: "new-inst",
        status: "qr_pending",
        qr: "1@test-qr,a,b,c",
        created_at: new Date().toISOString(),
      },
    });
  });
  await page.route(`${API}/stats/**`, (r) => r.fulfill({ json: {} }));
  await page.route(`${API}/proxy/**`, (r) => r.fulfill({ json: {} }));
  await page.route(`${API}/health`, (r) =>
    r.fulfill({ json: { status: "ok", version: "0.3.0" } })
  );
  await page.route(`${API}/logs**`, (r) => r.fulfill({ json: { logs: [] } }));
  await page.route(`${API}/config/**`, (r) => r.fulfill({ json: {} }));
}

test.describe("Instances", () => {
  test("page renders with heading and description", async ({ page }) => {
    await mockInstanceApis(page);
    await page.goto("/instances");
    await expect(page.getByText("Gerencie suas conexoes WhatsApp")).toBeVisible({
      timeout: 5000,
    });
  });

  test("new instance button is visible", async ({ page }) => {
    await mockInstanceApis(page);
    await page.goto("/instances");
    await expect(
      page.getByRole("button", { name: "Nova Instancia" }).first()
    ).toBeVisible({ timeout: 5000 });
  });

  test("empty state shows when no instances", async ({ page }) => {
    await mockInstanceApis(page, []);
    await page.goto("/instances");
    await expect(page.getByText("Nenhuma instancia")).toBeVisible({ timeout: 5000 });
  });

  test("empty state has call-to-action button", async ({ page }) => {
    await mockInstanceApis(page, []);
    await page.goto("/instances");
    // Header button + empty state CTA button = 2
    const buttons = page.getByRole("button", { name: "Nova Instancia" });
    await expect(buttons).toHaveCount(2, { timeout: 5000 });
  });

  test("clicking new instance button opens dialog", async ({ page }) => {
    await mockInstanceApis(page);
    await page.goto("/instances");
    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await expect(page.locator("[role='dialog']")).toBeVisible({ timeout: 2000 });
  });
});
