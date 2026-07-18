#!/usr/bin/env node
/**
 * One-command Phase 0 quality gate.
 */
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const py = path.join(root, "backend", ".venv", "Scripts", "python.exe");

function run(cmd, cwd = root) {
  console.log(`\n==> ${cmd}`);
  execSync(cmd, { cwd, stdio: "inherit", env: process.env, shell: true });
}

run(`"${py}" -m ruff format --check app tests`, path.join(root, "backend"));
run(`"${py}" -m ruff check app tests`, path.join(root, "backend"));
run(`"${py}" -m mypy app`, path.join(root, "backend"));
run(`"${py}" -m pytest -q`, path.join(root, "backend"));
run(`"${py}" "${path.join(root, "scripts", "generate_json_schemas.py")}"`);
run("node scripts/generate-zod.mjs");
run("node scripts/check-contracts.mjs");
run("node scripts/proof-drift-fails.mjs");
run("npm run format:check", path.join(root, "frontend"));
run("npm run lint", path.join(root, "frontend"));
run("npm run typecheck", path.join(root, "frontend"));
run("npm test", path.join(root, "frontend"));
run("npm run build", path.join(root, "frontend"));
console.log("\nAll Phase 0 checks passed.");
