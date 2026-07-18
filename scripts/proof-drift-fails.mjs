#!/usr/bin/env node
/**
 * Prove that check-contracts fails when generated Zod is tampered.
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const target = path.join(
  root,
  "frontend",
  "src",
  "schemas",
  "generated",
  "HealthResponse.ts",
);
const original = readFileSync(target, "utf8");

try {
  writeFileSync(target, `${original}\n/* intentional drift */\n`, "utf8");
  let failed = false;
  try {
    execFileSync(process.execPath, [path.join(root, "scripts", "check-contracts.mjs")], {
      cwd: root,
      stdio: "pipe",
    });
  } catch {
    failed = true;
  }
  if (!failed) {
    console.error("expected check-contracts to fail after tamper");
    process.exit(1);
  }
  console.log("drift-check proof OK (tamper detected)");
} finally {
  // check-contracts regenerates clean output; ensure original restored if needed
  writeFileSync(target, original, "utf8");
  execFileSync(process.execPath, [path.join(root, "scripts", "generate-zod.mjs")], {
    cwd: root,
    stdio: "pipe",
  });
}
