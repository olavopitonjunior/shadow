import { test, expect } from "@playwright/test";

test("app loads successfully", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Shadow Admin" })
  ).toBeVisible();
});
