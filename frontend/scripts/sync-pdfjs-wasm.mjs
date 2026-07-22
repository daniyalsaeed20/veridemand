import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PDFJS_WASM_SRC = path.resolve(__dirname, "../node_modules/pdfjs-dist/wasm");
const PDFJS_WASM_DEST = path.resolve(__dirname, "../public/pdfjs-wasm");

const REQUIRED_WASM = ["jbig2.wasm", "openjpeg.wasm", "qcms_bg.wasm"];

/** Sync locked pdfjs-dist WASM codecs into public/pdfjs-wasm (fail if missing). */
export function syncPdfjsWasm() {
  if (!fs.existsSync(PDFJS_WASM_SRC)) {
    throw new Error(
      `pdfjs-dist WASM source missing at ${PDFJS_WASM_SRC}. Run pnpm install in frontend/.`,
    );
  }

  const sourceNames = new Set(
    fs
      .readdirSync(PDFJS_WASM_SRC, { withFileTypes: true })
      .filter((entry) => entry.isFile())
      .map((entry) => entry.name),
  );

  for (const required of REQUIRED_WASM) {
    if (!sourceNames.has(required)) {
      throw new Error(`Required PDF.js WASM codec missing from install: ${required}`);
    }
  }

  fs.mkdirSync(PDFJS_WASM_DEST, { recursive: true });

  for (const entry of fs.readdirSync(PDFJS_WASM_DEST, { withFileTypes: true })) {
    if (entry.isFile() && !sourceNames.has(entry.name)) {
      fs.unlinkSync(path.join(PDFJS_WASM_DEST, entry.name));
    }
  }

  for (const name of sourceNames) {
    fs.copyFileSync(path.join(PDFJS_WASM_SRC, name), path.join(PDFJS_WASM_DEST, name));
  }
}

const isDirectRun =
  process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isDirectRun) {
  syncPdfjsWasm();
  console.log(`synced WASM -> ${PDFJS_WASM_DEST}`);
}
