import { test, expect } from "@playwright/test";

test.describe("Costs", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/costs");
    await page.waitForTimeout(2000);
  });

  test("summary cards render", async ({ page }) => {
    await expect(page.getByText("Total Cost")).toBeVisible();
    await expect(page.getByText("Input Tokens")).toBeVisible();
    await expect(page.getByText("Output Tokens")).toBeVisible();
  });

  test("cost chart section is visible", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Cost Over Time (Last 30 Days)" })
    ).toBeVisible();
  });

  test("provider breakdown section is visible", async ({ page }) => {
    await expect(page.getByText("Provider Breakdown")).toBeVisible();
  });

  test("pricing configuration table is visible", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Pricing Configuration" })
    ).toBeVisible();
    const table = page.locator("table").last();
    const noData = page.getByText("No pricing data available");
    const tableOrEmpty = table.or(noData);
    await expect(tableOrEmpty.first()).toBeVisible();
  });
});
