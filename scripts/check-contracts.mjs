#!/usr/bin/env node
/**
 * Drift check: snapshot generated artifacts, regenerate from Pydantic, compare.
 * Fails when hand-edited Zod/JSON Schema would be overwritten by regeneration.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = path.join(root, "backend", ".venv", "Scripts", "python.exe");
const schemaDir = path.join(root, "contracts", "generated");
const zodDir = path.join(root, "frontend", "src", "schemas", "generated");

function snapshotDir(dir) {
  const out = {};
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    out[name] = readFileSync(path.join(dir, name), "utf8");
  }
  return out;
}

function compare(label, before, after) {
  const names = new Set([...Object.keys(before), ...Object.keys(after)]);
  const drifts = [];
  for (const name of names) {
    if ((before[name] ?? "") !== (after[name] ?? "")) {
      drifts.push(`${label}/${name}`);
    }
  }
  return drifts;
}

const beforeSchemas = snapshotDir(schemaDir);
const beforeZod = snapshotDir(zodDir);

execFileSync(python, [path.join(root, "scripts", "generate_json_schemas.py")], {
  cwd: root,
  stdio: "inherit",
});
execFileSync(process.execPath, [path.join(root, "scripts", "generate-zod.mjs")], {
  cwd: root,
  stdio: "inherit",
});

const drifts = [
  ...compare("contracts/generated", beforeSchemas, snapshotDir(schemaDir)),
  ...compare("frontend/src/schemas/generated", beforeZod, snapshotDir(zodDir)),
];

if (drifts.length) {
  console.error("Contract drift detected:");
  for (const d of drifts) console.error(`  - ${d}`);
  console.error("Run generate scripts and commit updated artifacts.");
  process.exit(1);
}

console.log("contracts:check OK — no drift");
