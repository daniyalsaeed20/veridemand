#!/usr/bin/env node
/**
 * Launch VeriDemand API from .venv-ocr with Phase 5 conservative page-vision
 * reservation enabled. Does not change the release default (feature-off).
 *
 * HANDWRITING_PAGE_VISION_FALLBACK_ENABLED=true
 * HANDWRITING_PAGE_VISION_FALLBACK_MODE=conservative
 *
 * Refuses to reuse a feature-off OCR backend on :8000.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWin = process.platform === "win32";
const venvPython = path.join(
  root,
  ".venv-ocr",
  isWin ? "Scripts" : "bin",
  isWin ? "python.exe" : "python",
);
const backendUrl = "http://127.0.0.1:8000";
const frontendUrl = "http://localhost:5173";

if (!existsSync(venvPython)) {
  console.error(
    "ERROR: .venv-ocr is missing. Run:\n  $env:UV_PROJECT_ENVIRONMENT='.venv-ocr'\n  uv sync --group ocr",
  );
  process.exit(2);
}

const env = {
  ...process.env,
  UV_PROJECT_ENVIRONMENT: ".venv-ocr",
  HANDWRITING_PAGE_VISION_FALLBACK_ENABLED: "true",
  HANDWRITING_PAGE_VISION_FALLBACK_MODE: "conservative",
};

function run(command, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      env,
      stdio: "inherit",
      shell: isWin,
      ...opts,
    });
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited with ${code}`));
    });
  });
}

function assertPortReusableOrFree() {
  const code = `
from scripts.lib.api_process_guard import commits_match, port_in_use, probe_live, repo_head
base = ${JSON.stringify(backendUrl)}
live = probe_live(base)
head = repo_head()
if live.reachable:
    profile = (live.configuration_profile or "")
    if commits_match(live.git_commit, head) and "page_vision_on" in profile:
        print("reuse")
    elif commits_match(live.git_commit, head):
        print(f"feature_mismatch profile={profile}")
    else:
        print(f"mismatch pid={live.process_id} live={live.git_commit} head={head}")
elif port_in_use("127.0.0.1", 8000):
    print("occupied")
else:
    print("free")
`;
  const result = spawnSync(venvPython, ["-c", code], {
    cwd: root,
    encoding: "utf8",
    env,
    windowsHide: true,
  });
  const out = (result.stdout || "").trim().toLowerCase();
  if (result.status !== 0) {
    console.error("ERROR: could not probe port 8000 for Phase 5 backend launch.");
    if (result.stderr) console.error(result.stderr.trim().slice(0, 400));
    process.exit(2);
  }
  if (out === "free") {
    return { reuse: false };
  }
  if (out === "reuse") {
    console.log(`Port 8000 already serves Phase 5 page_vision_on; reusing ${backendUrl}`);
    return { reuse: true };
  }
  console.error(
    `ERROR: port 8000 cannot be reused for pnpm dev:phase5.\n` +
      `  probe=${out}\n` +
      `  Stop the current VeriDemand backend (e.g. feature-off pnpm dev:ocr) and retry.\n` +
      `  Unrelated processes are never killed.`,
  );
  process.exit(2);
}

function printBanner(gitCommit) {
  console.log("");
  console.log("=== VeriDemand Phase 5 development profile ===");
  console.log("  Phase 5 conservative page-vision reservation: ENABLED");
  console.log("  HANDWRITING_PAGE_VISION_FALLBACK_ENABLED=true");
  console.log("  HANDWRITING_PAGE_VISION_FALLBACK_MODE=conservative");
  console.log("  Hybrid mode: not enabled");
  console.log(`  python_environment: .venv-ocr`);
  console.log(`  backend_url: ${backendUrl}`);
  console.log(`  frontend_url: ${frontendUrl}`);
  console.log(`  git_commit: ${gitCommit}`);
  console.log("  Note: pnpm dev / pnpm dev:ocr keep reservation OFF (release default).");
  console.log("==============================================");
  console.log("");
}

async function main() {
  const git = spawnSync("git", ["rev-parse", "HEAD"], {
    cwd: root,
    encoding: "utf8",
    windowsHide: true,
  });
  const gitCommit = (git.stdout || "").trim().slice(0, 40) || "unknown";
  printBanner(gitCommit);

  const port = assertPortReusableOrFree();
  if (port.reuse) {
    console.log("Phase 5 backend already running with matching build + page_vision_on; holding.");
    await new Promise(() => {});
    return;
  }

  console.log("Syncing OCR-only environment (.venv-ocr)...");
  await run("uv", ["sync", "--group", "ocr"]);
  console.log("Validating OCR backend environment...");
  await run("uv", ["run", "python", "scripts/check_ocr_backend_env.py"]);
  console.log("Starting uvicorn on http://127.0.0.1:8000 (Phase 5 reservation ON)...");
  const uvicorn = spawn(
    "uv",
    ["run", "uvicorn", "backend.app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
    { cwd: root, env, stdio: "inherit", shell: isWin },
  );
  const stop = () => {
    if (!uvicorn.killed) uvicorn.kill();
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
  uvicorn.on("exit", (code) => process.exit(code ?? 1));
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
