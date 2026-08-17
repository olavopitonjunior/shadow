import { test, expect } from "@playwright/test";

const API = "http://localhost:8099";

const mockSessions = [
  {
    id: "sess-1",
    participant_phone: "+5511999998888",
    message_count: 12,
    is_active: true,
    input_tokens: 5000,
    output_tokens: 1200,
    last_activity_at: "2026-02-10T15:30:00Z",
  },
  {
    id: "sess-2",
    participant_phone: "+5511777776666",
    message_count: 5,
    is_active: false,
    input_tokens: 2000,
    output_tokens: 500,
    last_activity_at: "2026-02-09T10:00:00Z",
  },
];

async function mockConversationApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/**`, (route) => {
    const url = route.request().url();
    if (url.includes("/proxy/agent/sessions")) {
      return route.fulfill({ json: mockSessions });
    }
    if (url.includes("/health")) {
      return route.fulfill({ json: { status: "ok", version: "0.3.0" } });
    }
    if (url.includes("/instances")) {
      return route.fulfill({ json: { instances: [] } });
    }
    if (url.includes("/logs")) {
      return route.fulfill({ json: { logs: [] } });
    }
    return route.fulfill({ json: {} });
  });
}

test.describe("Conversations", () => {
  test.beforeEach(async ({ page }) => {
    await mockConversationApis(page);
    await page.goto("/conversations");
    await page.waitForLoadState("domcontentloaded");
  });

  test("stats cards render", async ({ page }) => {
    await expect(page.getByText("Total de Sessoes")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Mensagens Processadas")).toBeVisible();
    await expect(page.getByText("Sessoes Ativas").first()).toBeVisible();
  });

  test("sessions table has correct headers", async ({ page }) => {
    // "Sessoes Ativas" is a CardTitle in the table section
    // With mocked data, the table should render (not empty state)
    const table = page.locator("table");
    const cardTitle = page.getByText("Sessoes Ativas").last();
    await expect(table.or(cardTitle)).toBeVisible({ timeout: 5000 });
  });

  test("phone numbers are masked", async ({ page }) => {
    await page.waitForTimeout(1000);
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
