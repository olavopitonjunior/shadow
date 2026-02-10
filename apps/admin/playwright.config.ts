import { defineConfig } from "@playwright/test";

const isHeadless = process.env.PW_HEADLESS === "1";

export default defineConfig({
  testDir: "./tests",
  timeout: 30000,
  expect: {
    timeout: 5000,
  },
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: isHeadless,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5173",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
  },
});
