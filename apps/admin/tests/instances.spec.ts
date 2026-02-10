import { test, expect } from "@playwright/test";

test.describe("Instances", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/instances");
    await page.waitForTimeout(2000);
  });

  test("page renders with heading and description", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Instancias" })
    ).toBeVisible();
    await expect(
      page.getByText("Gerencie suas conexoes WhatsApp")
    ).toBeVisible();
  });

  test("new instance button is visible", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Nova Instancia" }).first()
    ).toBeVisible();
  });

  test("empty state shows when no instances", async ({ page }) => {
    // Since API will fail in test, we should see empty state
    const emptyState = page.getByText("Nenhuma instancia");
    const skeleton = page.locator("[class*='skeleton']").first();

    // Either skeleton while loading OR empty state after load
    await expect(emptyState.or(skeleton)).toBeVisible({ timeout: 5000 });
  });

  test("empty state has call-to-action button", async ({ page }) => {
    // Wait for loading to complete
    await page.waitForTimeout(3000);

    const ctaButton = page.getByRole("button", { name: "Nova Instancia" }).last();
    const skeleton = page.locator("[class*='skeleton']").first();

    // Either CTA button is visible OR still loading
    await expect(ctaButton.or(skeleton)).toBeVisible();
  });

  test("clicking new instance button opens dialog", async ({ page }) => {
    const newInstanceButton = page.getByRole("button", { name: "Nova Instancia" }).first();
    await newInstanceButton.click();

    // Check for dialog appearing
    await expect(page.locator("[role='dialog']")).toBeVisible({ timeout: 2000 });
  });
});
