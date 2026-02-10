import { test, expect } from "@playwright/test";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Wait for API data to load
    await page.waitForTimeout(2000);
  });

  test("health badges are visible", async ({ page }) => {
    await expect(page.getByText("Agent:")).toBeVisible();
    await expect(page.getByText("Gateway:")).toBeVisible();
    await expect(page.getByText("Storage:")).toBeVisible();
    await expect(page.getByText("Scheduler:")).toBeVisible();
  });

  test("stats cards render with data", async ({ page }) => {
    await expect(page.getByText("Total Messages")).toBeVisible();
    await expect(page.getByText("Active Sessions")).toBeVisible();
    await expect(page.getByText("Pending Tasks")).toBeVisible();
    await expect(page.getByText("Upcoming Appointments")).toBeVisible();
  });

  test("token usage chart section is visible", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Token Usage (Last 7 Days)" })
    ).toBeVisible();
  });

  test("WhatsApp connections section is visible", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "WhatsApp Connections" })
    ).toBeVisible();
  });

  test("recent activity section is visible", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Recent Activity" })
    ).toBeVisible();
  });
});
