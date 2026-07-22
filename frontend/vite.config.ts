import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

const here = path.dirname(fileURLToPath(import.meta.url));
const syncScript = path.join(here, "scripts", "sync-pdfjs-wasm.mjs");

function syncPdfjsWasm(): void {
  const result = spawnSync(process.execPath, [syncScript], {
    cwd: here,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    throw new Error(`PDF.js WASM sync failed (exit ${result.status ?? "unknown"})`);
  }
}

/** Keep unhashed pdfjs-dist WASM codecs available at `/pdfjs-wasm/` for getDocument. */
function pdfjsWasmPlugin(): Plugin {
  return {
    name: "veridemand-pdfjs-wasm",
    buildStart() {
      syncPdfjsWasm();
    },
    configureServer() {
      syncPdfjsWasm();
    },
  };
}

export default defineConfig({
  plugins: [react(), pdfjsWasmPlugin()],
  server: {
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/tests/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    env: {
      VITE_API_BASE_URL: "http://127.0.0.1:8000",
    },
  },
});
