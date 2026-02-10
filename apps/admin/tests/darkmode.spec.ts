import { test, expect } from "@playwright/test";

test.describe("Dark Mode", () => {
  test("toggle changes dark class on html element", async ({ page }) => {
    await page.goto("/");

    const htmlElement = page.locator("html");
    const initialDark = await htmlElement.evaluate((el) =>
      el.classList.contains("dark")
    );

    // Click the theme toggle button (only button in the header)
    const toggleBtn = page.locator("header").getByRole("button");
    await toggleBtn.click();

    const afterToggle = await htmlElement.evaluate((el) =>
      el.classList.contains("dark")
    );
    expect(afterToggle).toBe(!initialDark);
  });

  test("preference persists after reload", async ({ page }) => {
    await page.goto("/");

    // Set dark mode via localStorage
    await page.evaluate(() => {
      localStorage.setItem("theme", "dark");
    });
    await page.reload();

    const isDark = await page
      .locator("html")
      .evaluate((el) => el.classList.contains("dark"));
    expect(isDark).toBe(true);
  });

  test("background changes between light and dark", async ({ page }) => {
    await page.goto("/");

    // Set light mode
    await page.evaluate(() => {
      localStorage.setItem("theme", "light");
      document.documentElement.classList.remove("dark");
    });

    const lightBg = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue(
        "--background"
      )
    );

    // Switch to dark mode
    await page.evaluate(() => {
      localStorage.setItem("theme", "dark");
      document.documentElement.classList.add("dark");
    });

    const darkBg = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue(
        "--background"
      )
    );

    expect(lightBg).not.toBe(darkBg);
  });
});
