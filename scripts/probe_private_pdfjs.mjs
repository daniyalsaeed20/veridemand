/**
 * Local Playwright harness: render every page of the private corpus with
 * PDF.js and report blank pages. Not part of CI (private fixtures).
 */
import { chromium } from "@playwright/test";
import { createHash } from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const privateDir = path.join(root, "fixtures", "private");
const pdfjsBuild = path.join(
  root,
  "frontend",
  "node_modules",
  "pdfjs-dist",
  "build",
);
const wasmDir = path.join(
  root,
  "frontend",
  "node_modules",
  "pdfjs-dist",
  "wasm",
);

const files = fs
  .readdirSync(privateDir)
  .filter((name) => name.toLowerCase().endsWith(".pdf"))
  .sort();

/** Opaque label so private filenames never appear in probe stdout. */
function corpusLabel(name) {
  return createHash("sha256").update(name, "utf8").digest("hex").slice(0, 12);
}

function contentType(filePath) {
  if (filePath.endsWith(".mjs")) return "text/javascript";
  if (filePath.endsWith(".wasm")) return "application/wasm";
  if (filePath.endsWith(".js")) return "application/javascript";
  return "application/octet-stream";
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://127.0.0.1");
  if (url.pathname.startsWith("/pdfjs/")) {
    const filePath = path.join(
      pdfjsBuild,
      url.pathname.slice("/pdfjs/".length),
    );
    if (!filePath.startsWith(pdfjsBuild) || !fs.existsSync(filePath)) {
      res.writeHead(404);
      res.end();
      return;
    }
    res.writeHead(200, { "Content-Type": contentType(filePath) });
    fs.createReadStream(filePath).pipe(res);
    return;
  }
  if (url.pathname.startsWith("/wasm/")) {
    const filePath = path.join(wasmDir, url.pathname.slice("/wasm/".length));
    if (!filePath.startsWith(wasmDir) || !fs.existsSync(filePath)) {
      res.writeHead(404);
      res.end();
      return;
    }
    res.writeHead(200, { "Content-Type": contentType(filePath) });
    fs.createReadStream(filePath).pipe(res);
    return;
  }
  if (url.pathname === "/") {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(`<!doctype html><html><body><canvas id="c"></canvas>
<script type="module">
import * as pdfjs from "/pdfjs/pdf.min.mjs";
pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
window.__pdfjs = pdfjs;
window.__ready = true;
</script></body></html>`);
    return;
  }
  res.writeHead(404);
  res.end();
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();
const origin = `http://127.0.0.1:${port}`;

async function probe(page, bytes, isolation) {
  await page.goto(origin);
  await page.waitForFunction(() => window.__ready === true, null, {
    timeout: 30_000,
  });
  return page.evaluate(
    async ({ data, isolation: iso }) => {
      const pdfjs = window.__pdfjs;
      const loadingTask = pdfjs.getDocument({
        data: Uint8Array.from(data),
        wasmUrl: "/wasm/",
        useWasm: true,
        disableRange: iso,
        disableStream: iso,
        disableAutoFetch: iso,
      });
      const doc = await loadingTask.promise;
      const blank = [];
      for (let n = 1; n <= doc.numPages; n += 1) {
        const pdfPage = await doc.getPage(n);
        const viewport = pdfPage.getViewport({ scale: 1 });
        const canvas = document.getElementById("c");
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        await pdfPage.render({
          canvas,
          viewport,
          intent: "display",
          background: "rgb(255,255,255)",
          optionalContentConfigPromise: doc.getOptionalContentConfig({
            intent: "display",
          }),
        }).promise;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        const { data: pixels } = ctx.getImageData(
          0,
          0,
          canvas.width,
          canvas.height,
        );
        let ink = 0;
        for (let i = 0; i < pixels.length; i += 16) {
          const r = pixels[i];
          const g = pixels[i + 1];
          const b = pixels[i + 2];
          const a = pixels[i + 3];
          if (a > 8 && (r < 245 || g < 245 || b < 245)) {
            ink += 1;
          }
        }
        if (ink === 0) blank.push(n);
      }
      const pages = doc.numPages;
      try {
        if (typeof doc.cleanup === "function") doc.cleanup();
      } catch {
        // ignore
      }
      return { pages, blank };
    },
    { data: Array.from(bytes), isolation },
  );
}

if (files.length === 0) {
  console.error("No private PDFs found under fixtures/private/");
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage();
page.on("console", (msg) => {
  if (msg.type() === "error" || msg.type() === "warning") {
    const text = msg.text();
    if (
      text.includes("wasmUrl") ||
      text.includes("Jbig2") ||
      text.includes("JBIG2")
    ) {
      console.log("BROWSER", msg.type(), text.slice(0, 240));
    }
  }
});

let failed = false;
for (const name of files) {
  const bytes = fs.readFileSync(path.join(privateDir, name));
  try {
    const ranged = await probe(page, bytes, false);
    const iso = await probe(page, bytes, true);
    const row = {
      corpusLabel: corpusLabel(name),
      pages: ranged.pages,
      blankWithRange: ranged.blank,
      blankIsolation: iso.blank,
    };
    console.log(JSON.stringify(row));
    if (ranged.blank.length > 0 || iso.blank.length > 0) {
      failed = true;
    }
  } catch (err) {
    console.log(
      JSON.stringify({ corpusLabel: corpusLabel(name), error: String(err) }),
    );
    failed = true;
  }
}
await browser.close();
server.close();
process.exit(failed ? 1 : 0);
