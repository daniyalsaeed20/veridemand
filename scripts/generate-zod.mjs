#!/usr/bin/env node
/**
 * Generate Zod schemas from contracts/generated/*.schema.json
 * using json-schema-to-zod. Output is committed under frontend/src/schemas/generated/.
 */
import { createRequire } from "node:module";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const schemaDir = path.join(root, "contracts", "generated");
const outDir = path.join(root, "frontend", "src", "schemas", "generated");
const require = createRequire(path.join(root, "frontend", "package.json"));
const { jsonSchemaToZod } = require("json-schema-to-zod");

mkdirSync(outDir, { recursive: true });

const files = readdirSync(schemaDir).filter((f) => f.endsWith(".schema.json"));
if (files.length === 0) {
  console.error("No JSON schemas found. Run scripts/generate_json_schemas.py first.");
  process.exit(1);
}

const exports = [];

for (const file of files) {
  const name = file.replace(/\.schema\.json$/, "");
  const schema = JSON.parse(readFileSync(path.join(schemaDir, file), "utf8"));
  const zodBody = jsonSchemaToZod(schema, { module: "esm", name: `${name}Schema` });
  const outPath = path.join(outDir, `${name}.ts`);
  const content = `/* AUTO-GENERATED — do not edit by hand. */\n${zodBody}\n`;
  writeFileSync(outPath, content, "utf8");
  exports.push(`export { ${name}Schema } from "./${name}";`);
  console.log(`wrote ${path.relative(root, outPath)}`);
}

writeFileSync(
  path.join(outDir, "index.ts"),
  `/* AUTO-GENERATED — do not edit by hand. */\n${exports.sort().join("\n")}\n`,
  "utf8",
);
console.log(`generated ${files.length} Zod modules`);
