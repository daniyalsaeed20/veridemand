#!/usr/bin/env node
/**
 * Launch the VeriDemand API from the OCR-only environment (.venv-ocr).
 * Fails loudly if the environment is missing, contains Torch, or cannot import Paddle.
 */
import { spawn } from "node:child_process";
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

async function main() {
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
