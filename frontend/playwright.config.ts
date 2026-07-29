import { defineConfig, devices } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const configDir = path.dirname(fileURLToPath(import.meta.url));

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

const nodeProcess = (
  globalThis as { process?: { env?: Record<string, string | undefined>; platform?: string } }
).process;
const isCI = Boolean(nodeProcess?.env?.CI);
const pythonBin =
  nodeProcess?.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

type PortProbe = "match" | "mismatch" | "occupied" | "free" | "unavailable";

function probeBackend(baseUrl: string): PortProbe {
  if (isCI) {
    return "free";
  }
  const root = path.resolve(configDir, "..");
  const py = path.join(root, pythonBin);
  if (!existsSync(py)) {
    return "unavailable";
  }
  const code = `
from scripts.lib.api_process_guard import (
    commits_match,
    parse_host_port,
    port_in_use,
    probe_live,
    repo_head,
)
base = ${JSON.stringify(baseUrl)}
host, port = parse_host_port(base)
live = probe_live(base)
head = repo_head()
if live.reachable:
    print("match" if commits_match(live.git_commit, head) else "mismatch")
elif port_in_use(host, port):
    print("occupied")
else:
    print("free")
`;
  try {
    const out = execFileSync(py, ["-c", code], {
      cwd: root,
      encoding: "utf8",
      timeout: 8_000,
      windowsHide: true,
    })
      .trim()
      .toLowerCase();
    if (out === "match" || out === "mismatch" || out === "occupied" || out === "free") {
      return out;
    }
    return "unavailable";
  } catch {
    return "unavailable";
  }
}

function assertBackendReusableOrFree(label: string, baseUrl: string): boolean {
  const status = probeBackend(baseUrl);
  if (status === "match") {
    return true;
  }
  if (status === "mismatch" || status === "occupied") {
    throw new Error(
      `Playwright ${label} backend at ${baseUrl} is occupied by a process that ` +
        `does not match this repository HEAD (or is not a reachable VeriDemand API). ` +
        `Stop the obsolete VeriDemand process or free the port before running E2E. ` +
        `Unrelated processes are never killed. (probe=${status})`,
    );
  }
  // free / unavailable → Playwright starts a new server (reuseExistingServer false).
  return false;
}

const reuseNormalBackend = isCI ? false : assertBackendReusableOrFree("normal", NORMAL_BACKEND);
const reuseHoldsBackend = isCI ? false : assertBackendReusableOrFree("holds", HOLDS_BACKEND);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: isCI,
  // Holds stack can miss the first session create after a long chromium suite;
  // one retry matches CI and avoids false local gate failures.
  retries: 1,
  workers: 1,
  // Phase 4 printed OCR is covered by smoke/OCR jobs; default e2e stays Phase 2/3-speed.
  timeout: 120_000,
  expect: {
    timeout: 90_000,
  },
  reporter: [["html", { open: "never" }]],
  use: {
    trace: "on-first-retry",
    actionTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      testIgnore: HOLDS_SPECS,
      use: { ...devices["Desktop Chrome"], baseURL: NORMAL_FRONTEND },
      timeout: 120_000,
    },
    {
      name: "chromium-holds",
      testMatch: HOLDS_SPECS,
      use: { ...devices["Desktop Chrome"], baseURL: HOLDS_FRONTEND },
      // Holds specs stay short (cancel/TTL); keep a tighter budget.
      timeout: 90_000,
    },
  ],
  webServer: [
    {
      command: `${pythonBin} -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`,
      cwd: "..",
      url: `${NORMAL_BACKEND}/health/live`,
      reuseExistingServer: reuseNormalBackend,
      timeout: 120_000,
      env: {
        OCR_ENABLED: nodeProcess?.env?.OCR_ENABLED ?? "false",
      },
    },
    {
      command: "pnpm dev",
      url: NORMAL_FRONTEND,
      reuseExistingServer: !isCI,
      timeout: 120_000,
    },
    {
      command: `${pythonBin} -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010`,
      cwd: "..",
      url: `${HOLDS_BACKEND}/health/live`,
      reuseExistingServer: reuseHoldsBackend,
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
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        VITE_API_BASE_URL: HOLDS_BACKEND,
      },
    },
  ],
});
