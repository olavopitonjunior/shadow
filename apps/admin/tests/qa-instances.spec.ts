/**
 * QA Tests: Instance Management (Mocked API)
 *
 * Tests the full instance lifecycle UI with intercepted API routes.
 * Does NOT require real services — all responses are mocked.
 */
import { test, expect, type Route } from "@playwright/test";
import {
  instanceMockConnected,
  instanceMockQrPending,
  instanceMockDisconnected,
  instanceStatsMock,
  instanceConversationsMock,
  instanceCostsMock,
  instanceLogsMock,
} from "./mocks";

const API = "http://localhost:8099";

// Helper: mock all background requests so pages load cleanly
async function mockBackground(page: import("@playwright/test").Page) {
  await page.route(`${API}/stats/**`, (r) => r.fulfill({ json: {} }));
  await page.route(`${API}/proxy/**`, (r) => r.fulfill({ json: {} }));
  await page.route(`${API}/logs/**`, (r) => r.fulfill({ json: { logs: [] } }));
  await page.route(`${API}/logs?*`, (r) => r.fulfill({ json: { logs: [] } }));
  await page.route(`${API}/health`, (r) =>
    r.fulfill({ json: { status: "ok", version: "0.3.0" } })
  );
  await page.route(`${API}/config/**`, (r) => r.fulfill({ json: {} }));
}

// ─── Grupo 1: Navegação & Layout ─────────────────────────────

test.describe("G1: Navegação & Layout", () => {
  test("sidebar tem link Instancias", async ({ page }) => {
    await page.goto("/");
    const link = page.locator("aside").getByRole("link", { name: "Instancias" });
    await expect(link).toBeVisible();
  });

  test("clicar Instancias navega para /instances", async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances`, (r) =>
      r.fulfill({ json: { instances: [] } })
    );
    await page.goto("/");
    await page.getByRole("link", { name: "Instancias" }).click();
    await expect(page).toHaveURL(/\/instances/);
  });

  test("header mostra titulo Instancias", async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances`, (r) =>
      r.fulfill({ json: { instances: [] } })
    );
    await page.goto("/instances");
    await expect(
      page.getByRole("heading", { name: "Instancias" })
    ).toBeVisible();
  });
});

// ─── Grupo 2: Lista vazia ────────────────────────────────────

test.describe("G2: Lista vazia", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances`, (r) =>
      r.fulfill({ json: { instances: [] } })
    );
    await page.goto("/instances");
  });

  test("mostra Nenhuma instancia", async ({ page }) => {
    await expect(page.getByText("Nenhuma instancia")).toBeVisible({
      timeout: 5000,
    });
  });

  test("botao Nova Instancia no header", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Nova Instancia" }).first()
    ).toBeVisible();
  });

  test("botao Nova Instancia no empty state", async ({ page }) => {
    await page.waitForTimeout(1000);
    const buttons = page.getByRole("button", { name: "Nova Instancia" });
    await expect(buttons).toHaveCount(2);
  });
});

// ─── Grupo 3: Lista com dados ────────────────────────────────

test.describe("G3: Lista com dados", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances`, (r) =>
      r.fulfill({
        json: {
          instances: [
            instanceMockConnected,
            instanceMockQrPending,
            instanceMockDisconnected,
          ],
        },
      })
    );
    await page.goto("/instances");
  });

  test("cards renderizam com nome correto", async ({ page }) => {
    await expect(page.getByText("WhatsApp Pessoal")).toBeVisible();
    await expect(page.getByText("WhatsApp Empresa")).toBeVisible();
    await expect(page.getByText("WhatsApp Antigo")).toBeVisible();
  });

  test("badge verde para connected", async ({ page }) => {
    await expect(page.getByText("Conectado", { exact: true })).toBeVisible();
  });

  test("badge amarelo para qr_pending", async ({ page }) => {
    await expect(page.getByText("QR Pendente")).toBeVisible();
  });

  test("badge outline para disconnected", async ({ page }) => {
    await expect(page.getByText("Desconectado")).toBeVisible();
  });

  test("botao Ver detalhes em cada card", async ({ page }) => {
    const buttons = page.getByRole("button", { name: "Ver detalhes" });
    await expect(buttons).toHaveCount(3);
  });

  test("telefone mascarado no card conectado", async ({ page }) => {
    await expect(page.getByText("...9999")).toBeVisible();
  });
});

// ─── Grupo 4: Dialog de criação (3 steps) ────────────────────

test.describe("G4: Dialog de criação", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances`, (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: { instances: [] } });
      }
      // POST — create instance
      return route.fulfill({
        json: {
          id: "new-inst",
          name: "Teste QA",
          gateway_user_id: "new-inst",
          status: "qr_pending",
          qr: "1@test-qr-data-for-display,abc,def,ghi",
          created_at: new Date().toISOString(),
          phone: null,
          connected_at: null,
          disconnected_at: null,
        },
      });
    });
    await page.goto("/instances");
  });

  test("clicar Nova Instancia abre dialog", async ({ page }) => {
    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await expect(page.locator("[role='dialog']")).toBeVisible();
    await expect(page.getByText("Nova Instancia").last()).toBeVisible();
  });

  test("dialog mostra input com placeholder", async ({ page }) => {
    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    const input = page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...");
    await expect(input).toBeVisible();
  });

  test("botao Criar desabilitado com input vazio", async ({ page }) => {
    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    const criar = page.locator("[role='dialog']").getByRole("button", { name: "Criar" });
    await expect(criar).toBeDisabled();
  });

  test("criar instancia avanca para step QR", async ({ page }) => {
    // Mock status polling
    let calls = 0;
    await page.route(`${API}/instances/new-inst/status`, (r) => {
      calls++;
      r.fulfill({
        json: { status: "qr_pending", phone: null, qr: "1@qr-data,a,b,c" },
      });
    });
    await page.route(`${API}/instances/new-inst/qr`, (r) =>
      r.fulfill({ json: { qr: "1@qr-data,a,b,c", status: "qr_pending" } })
    );

    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...").fill("Teste QA");
    await page.locator("[role='dialog']").getByRole("button", { name: "Criar" }).click();

    // Should see QR step
    await expect(page.getByText("Conectar WhatsApp")).toBeVisible({ timeout: 5000 });
  });

  test("QR code SVG renderiza no dialog", async ({ page }) => {
    await page.route(`${API}/instances/new-inst/status`, (r) =>
      r.fulfill({
        json: { status: "qr_pending", phone: null, qr: "1@mock-qr-string,a,b,c" },
      })
    );
    await page.route(`${API}/instances/new-inst/qr`, (r) =>
      r.fulfill({ json: { qr: "1@mock-qr-string,a,b,c", status: "qr_pending" } })
    );

    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...").fill("Teste QA");
    await page.locator("[role='dialog']").getByRole("button", { name: "Criar" }).click();

    // Wait for QR SVG to appear (use first() since dialog may have multiple SVGs)
    await expect(page.locator("[role='dialog'] svg").first()).toBeVisible({ timeout: 8000 });
  });

  test("polling detecta connected e avanca step", async ({ page }) => {
    let statusCalls = 0;
    await page.route(`${API}/instances/new-inst/status`, (r) => {
      statusCalls++;
      if (statusCalls >= 3) {
        return r.fulfill({
          json: { status: "connected", phone: "+5511999999999", qr: null },
        });
      }
      return r.fulfill({
        json: { status: "qr_pending", phone: null, qr: "1@qr,a,b,c" },
      });
    });
    await page.route(`${API}/instances/new-inst/qr`, (r) =>
      r.fulfill({ json: { qr: "1@qr,a,b,c", status: "qr_pending" } })
    );

    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...").fill("Teste QA");
    await page.locator("[role='dialog']").getByRole("button", { name: "Criar" }).click();

    // Wait for connected step
    await expect(page.getByText("Conectado!")).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("+5511999999999")).toBeVisible();
  });

  test("step connected tem botoes Fechar e Ver Instancia", async ({ page }) => {
    await page.route(`${API}/instances/new-inst/status`, (r) =>
      r.fulfill({
        json: { status: "connected", phone: "+5511999999999", qr: null },
      })
    );

    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...").fill("Teste QA");
    await page.locator("[role='dialog']").getByRole("button", { name: "Criar" }).click();

    await expect(page.getByText("Conectado!")).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: "Fechar" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Ver Instancia" })).toBeVisible();
  });

  test("erro de criacao mostra alerta no dialog", async ({ page }) => {
    // Override POST to fail
    await page.route(`${API}/instances`, (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({ status: 500, json: { detail: "Storage unavailable" } });
      }
      return route.fulfill({ json: { instances: [] } });
    });

    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...").fill("Falha");
    await page.locator("[role='dialog']").getByRole("button", { name: "Criar" }).click();

    await expect(page.getByText(/Erro ao criar instancia/)).toBeVisible({ timeout: 5000 });
  });

  test("Fechar fecha dialog e limpa estado", async ({ page }) => {
    await page.route(`${API}/instances/new-inst/status`, (r) =>
      r.fulfill({ json: { status: "connected", phone: "+55119", qr: null } })
    );

    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...").fill("Teste");
    await page.locator("[role='dialog']").getByRole("button", { name: "Criar" }).click();
    await expect(page.getByText("Conectado!")).toBeVisible({ timeout: 15000 });

    await page.getByRole("button", { name: "Fechar" }).click();
    await expect(page.locator("[role='dialog']")).not.toBeVisible();
  });
});

// ─── Grupo 5: InstanceCard Dropdown ──────────────────────────

test.describe("G5: Card dropdown", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances`, (route) => {
      if (route.request().method() !== "GET") {
        return route.fulfill({ json: { status: "ok" } });
      }
      return route.fulfill({
        json: { instances: [instanceMockConnected, instanceMockDisconnected] },
      });
    });
    // Mock action endpoints
    await page.route(`${API}/instances/*/connect`, (r) =>
      r.fulfill({ json: { id: "x", status: "connecting", qr: "qr" } })
    );
    await page.route(`${API}/instances/*/disconnect`, (r) =>
      r.fulfill({ json: { id: "x", status: "disconnected" } })
    );
    await page.route(`${API}/instances/*`, (route) => {
      if (route.request().method() === "DELETE") {
        return route.fulfill({ json: { status: "deleted" } });
      }
      return route.continue();
    });
    await page.goto("/instances");
  });

  test("dropdown abre com opcoes corretas para connected", async ({ page }) => {
    // Click the first dropdown (connected instance) — Radix adds aria-haspopup
    const dropdowns = page.locator("button[aria-haspopup='menu']");
    await dropdowns.first().click();

    // Use menuitem role to avoid matching "Ver detalhes" buttons on cards
    await expect(page.getByRole("menuitem", { name: "Ver detalhes" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Desconectar" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Remover" })).toBeVisible();
  });

  test("dropdown abre com opcoes corretas para disconnected", async ({ page }) => {
    const dropdowns = page.locator("button[aria-haspopup='menu']");
    await dropdowns.last().click();

    await expect(page.getByRole("menuitem", { name: "Ver detalhes" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Conectar" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Remover" })).toBeVisible();
  });

  test("Ver detalhes navega para /instances/:id", async ({ page }) => {
    // Mock detail page endpoints
    await page.route(`${API}/instances/inst-001`, (r) =>
      r.fulfill({ json: instanceMockConnected })
    );
    await page.route(`${API}/instances/inst-001/**`, (r) =>
      r.fulfill({ json: instanceStatsMock })
    );

    const dropdowns = page.locator("button[aria-haspopup='menu']");
    await dropdowns.first().click();
    await page.getByRole("menuitem", { name: "Ver detalhes" }).click();
    await expect(page).toHaveURL(/\/instances\/inst-001/);
  });
});

// ─── Grupo 6: Página de Detalhes ─────────────────────────────

test.describe("G6: Detalhes", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances/inst-001`, (r) => {
      if (r.request().method() === "GET") {
        return r.fulfill({ json: instanceMockConnected });
      }
      return r.fulfill({ json: { status: "ok" } });
    });
    await page.route(`${API}/instances/inst-001/stats`, (r) =>
      r.fulfill({ json: instanceStatsMock })
    );
    await page.route(`${API}/instances/inst-001/conversations`, (r) =>
      r.fulfill({ json: instanceConversationsMock })
    );
    await page.route(`${API}/instances/inst-001/costs`, (r) =>
      r.fulfill({ json: instanceCostsMock })
    );
    await page.route(`${API}/instances/inst-001/logs`, (r) =>
      r.fulfill({ json: instanceLogsMock })
    );
    await page.route(`${API}/instances/inst-001/connect`, (r) =>
      r.fulfill({ json: { id: "inst-001", status: "connecting" } })
    );
    await page.route(`${API}/instances/inst-001/disconnect`, (r) =>
      r.fulfill({ json: { id: "inst-001", status: "disconnected" } })
    );
    await page.goto("/instances/inst-001");
  });

  test("header mostra nome e badge", async ({ page }) => {
    await expect(page.getByText("WhatsApp Pessoal")).toBeVisible();
    await expect(page.getByText("Conectado", { exact: true })).toBeVisible();
  });

  test("botao Desconectar visivel para connected", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /Desconectar/ })
    ).toBeVisible();
  });

  test("botao Voltar navega para /instances", async ({ page }) => {
    await page.route(`${API}/instances`, (r) =>
      r.fulfill({ json: { instances: [] } })
    );
    await page.getByRole("button", { name: /Instancias/ }).click();
    await expect(page).toHaveURL(/\/instances$/);
  });

  test("tab Geral mostra stat cards", async ({ page }) => {
    await expect(page.getByText("Telefone")).toBeVisible();
    await expect(page.getByText("Mensagens")).toBeVisible();
    await expect(page.getByText("Sessoes")).toBeVisible();
    await expect(page.getByText("Custo Total")).toBeVisible();
  });

  test("tab Conversas mostra tabela", async ({ page }) => {
    await page.getByRole("tab", { name: /Conversas/ }).click();
    await expect(page.getByText("...6666")).toBeVisible({ timeout: 3000 });
  });

  test("tab Custos mostra providers", async ({ page }) => {
    await page.getByRole("tab", { name: /Custos/ }).click();
    await expect(page.getByText("anthropic")).toBeVisible({ timeout: 3000 });
  });

  test("tab Logs mostra tabela", async ({ page }) => {
    await page.getByRole("tab", { name: /Logs/ }).click();
    await expect(page.getByText("2026-02-10")).toBeVisible({ timeout: 3000 });
  });
});

// ─── Grupo 7: QR Code Display ────────────────────────────────

test.describe("G7: QR Code", () => {
  test("mostra Aguardando conexao com QR", async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances`, (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          json: {
            id: "qr-test",
            name: "QR",
            gateway_user_id: "qr-test",
            status: "qr_pending",
            qr: "2@some-qr-string,a,b,c",
            created_at: new Date().toISOString(),
          },
        });
      }
      return route.fulfill({ json: { instances: [] } });
    });
    await page.route(`${API}/instances/qr-test/status`, (r) =>
      r.fulfill({
        json: { status: "qr_pending", phone: null, qr: "2@some-qr-string,a,b,c" },
      })
    );
    await page.route(`${API}/instances/qr-test/qr`, (r) =>
      r.fulfill({ json: { qr: "2@some-qr-string,a,b,c", status: "qr_pending" } })
    );

    await page.goto("/instances");
    await page.getByRole("button", { name: "Nova Instancia" }).first().click();
    await page.getByPlaceholder("Ex: Meu WhatsApp, Empresa...").fill("QR");
    await page.locator("[role='dialog']").getByRole("button", { name: "Criar" }).click();

    await expect(page.getByText("Aguardando conexao...")).toBeVisible({
      timeout: 10000,
    });
  });
});

// ─── Grupo 8: Error Handling ─────────────────────────────────

test.describe("G8: Errors", () => {
  test("erro de mutação mostra alerta", async ({ page }) => {
    await mockBackground(page);
    // List loads fine, but connect mutation fails
    await page.route(`${API}/instances`, (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          json: { instances: [instanceMockDisconnected] },
        });
      }
      return route.continue();
    });
    await page.route(`${API}/instances/inst-003/connect`, (r) =>
      r.abort("connectionrefused")
    );

    await page.goto("/instances");
    await page.waitForTimeout(1000);

    // Trigger connect via dropdown (will fail)
    const dropdown = page.locator("button[aria-haspopup='menu']").first();
    await dropdown.click();
    await page.getByRole("menuitem", { name: "Conectar" }).click();

    // Error should appear from mutation failure
    await expect(
      page.getByText("Nao foi possivel conectar ao servidor")
    ).toBeVisible({ timeout: 8000 });
  });

  test("botao X fecha alerta de erro", async ({ page }) => {
    await mockBackground(page);
    await page.route(`${API}/instances`, (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          json: { instances: [instanceMockDisconnected] },
        });
      }
      return route.continue();
    });
    await page.route(`${API}/instances/inst-003/connect`, (r) =>
      r.abort("connectionrefused")
    );

    await page.goto("/instances");
    await page.waitForTimeout(1000);

    // Trigger connect which will fail
    const dropdown = page.locator("button[aria-haspopup='menu']").first();
    await dropdown.click();
    await page.getByRole("menuitem", { name: "Conectar" }).click();

    const alert = page.getByText("Nao foi possivel conectar ao servidor");
    await expect(alert).toBeVisible({ timeout: 8000 });

    // Close the alert via X button
    await page.locator("div.text-destructive button, div.bg-destructive\\/10 button").last().click();
    await expect(alert).not.toBeVisible({ timeout: 3000 });
  });
});
