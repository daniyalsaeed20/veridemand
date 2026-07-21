import { defineConfig, devices } from "@playwright/test";

// Two independent stacks:
//  - "normal": default backend + dev server, for upload/queue/reset/refresh flows.
//  - "holds": a backend configured with a test-only admission hold and a short
//    session TTL, plus a dev server pointed at it, for cancellation and expiry.
// Using localhost origins so they match each backend's FRONTEND_ORIGIN (CORS).
const NORMAL_FRONTEND = "http://localhost:5173";
const NORMAL_BACKEND = "http://127.0.0.1:8000";
const HOLDS_FRONTEND = "http://localhost:5273";
const HOLDS_BACKEND = "http://127.0.0.1:8010";

const HOLDS_SPECS = /\.holds\.spec\.ts$/;

// Read CI without pulling in @types/node (no new frontend dependencies).
const isCI = Boolean(
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.CI,
);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: 1,
  timeout: 60_000,
  reporter: [["html", { open: "never" }]],
  use: {
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      testIgnore: HOLDS_SPECS,
      use: { ...devices["Desktop Chrome"], baseURL: NORMAL_FRONTEND },
    },
    {
      name: "chromium-holds",
      testMatch: HOLDS_SPECS,
      use: { ...devices["Desktop Chrome"], baseURL: HOLDS_FRONTEND },
    },
  ],
  webServer: [
    {
      command: "uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000",
      cwd: "..",
      url: `${NORMAL_BACKEND}/health/live`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "pnpm dev",
      url: NORMAL_FRONTEND,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8010",
      cwd: "..",
      url: `${HOLDS_BACKEND}/health/live`,
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        TEMP_ROOT: "./temp-e2e",
        FRONTEND_ORIGIN: HOLDS_FRONTEND,
        QUEUE_ADMISSION_TEST_DELAY_SECONDS: "3",
        SESSION_TTL_SECONDS: "15",
        SESSION_CLEANUP_INTERVAL_SECONDS: "2",
        SESSION_EXPIRING_WARNING_SECONDS: "6",
      },
    },
    {
      command: "pnpm dev --port 5273 --strictPort",
      url: HOLDS_FRONTEND,
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        VITE_API_BASE_URL: HOLDS_BACKEND,
      },
    },
  ],
});
