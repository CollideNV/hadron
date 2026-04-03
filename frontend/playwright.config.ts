import { defineConfig, devices } from "@playwright/test";

const backendPort = Number(process.env.HADRON_TEST_BACKEND_PORT) || 8000;
const frontendPort = Number(process.env.HADRON_TEST_FRONTEND_PORT) || 5173;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: `http://localhost:${frontendPort}`,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `HADRON_CONTROLLER_PORT=${backendPort} ../.venv/bin/python ../scripts/dummy_server.py`,
      port: backendPort,
      reuseExistingServer: true,
    },
    {
      command: `npx vite --port ${frontendPort}`,
      port: frontendPort,
      reuseExistingServer: true,
    },
  ],
});
