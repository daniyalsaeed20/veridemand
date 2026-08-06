#!/usr/bin/env node
/**
 * Full-app local launcher.
 * On Windows, always use the OCR-only stack (pnpm dev:ocr) so mixed .venv is never silent.
 * On other platforms, keep the historic concurrent backend+frontend default.
 */
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWin = process.platform === "win32";
const script = isWin ? "dev:ocr" : "dev:legacy";

if (isWin) {
  console.log("Windows detected: routing `pnpm dev` to OCR-only launcher (`pnpm dev:ocr`).");
  console.log("Frontend-only: pnpm dev:frontend");
}

const child = spawn("pnpm", ["run", script], {
  cwd: root,
  stdio: "inherit",
  shell: isWin,
  env: process.env,
});
child.on("exit", (code) => process.exit(code ?? 1));
