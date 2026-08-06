#!/usr/bin/env node
/**
 * Launch the VeriDemand API from the OCR-only environment (.venv-ocr).
 * Fails loudly if the environment is missing, contains Torch, or cannot import Paddle.
 * Refuses to start when port 8000 is occupied by a non-matching process (never kills).
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

if (!existsSync(venvPython)) {
  console.error(
    "ERROR: .venv-ocr is missing. Run:\n  $env:UV_PROJECT_ENVIRONMENT='.venv-ocr'\n  uv sync --group ocr",
  );
  process.exit(2);
}

const env = {
  ...process.env,
  UV_PROJECT_ENVIRONMENT: ".venv-ocr",
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
    if commits_match(live.git_commit, head):
        print("reuse")
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
    console.error("ERROR: could not probe port 8000 for OCR backend launch.");
    if (result.stderr) console.error(result.stderr.trim().slice(0, 400));
    process.exit(2);
  }
  if (out === "free") {
    return { reuse: false };
  }
  if (out === "reuse") {
    console.log(`Port 8000 already serves a matching VeriDemand build; reusing ${backendUrl}`);
    return { reuse: true };
  }
  console.error(
    `ERROR: port 8000 is occupied by a process that is not this repository HEAD.\n` +
      `  probe=${out}\n` +
      `  Stop the obsolete VeriDemand backend (or free the port) before pnpm dev:ocr.\n` +
      `  Unrelated processes are never killed.`,
  );
  process.exit(2);
}

async function main() {
  const port = assertPortReusableOrFree();
  if (port.reuse) {
    // Keep process alive so concurrently does not exit the frontend partner.
    console.log("OCR backend already running with matching build identity; holding process.");
    await new Promise(() => {});
    return;
  }

  console.log("Syncing OCR-only environment (.venv-ocr)...");
  await run("uv", ["sync", "--group", "ocr"]);
  console.log("Validating OCR backend environment...");
  await run("uv", ["run", "python", "scripts/check_ocr_backend_env.py"]);
  console.log("Starting uvicorn on http://127.0.0.1:8000 ...");
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
