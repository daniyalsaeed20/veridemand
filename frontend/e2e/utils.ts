import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));

// Synthetic, safe upload fixtures generated under the repo root. No private data.
export const UPLOADS_DIR = path.resolve(HERE, "..", "..", "fixtures", "synthetic", "uploads");
export const NATIVE_DIR = path.resolve(HERE, "..", "..", "fixtures", "synthetic", "native");

export function fixture(name: string): string {
  if (name.startsWith("native/")) {
    return path.join(NATIVE_DIR, name.slice("native/".length));
  }
  return path.join(UPLOADS_DIR, name);
}

/** Queue/doc ready after Phase 3 native + Phase 4 printed OCR (progress capped at 65%). */
export const PROCESSING_COMPLETE_RE =
  /Printed OCR complete|Printed visual OCR complete|Native text accepted|requires visual processing|native text layer was rejected|No native text is available|canonical document ready|ready for extraction|Decision:\s*accepted/i;

export async function waitForProcessingComplete(page: Page, timeout = 180_000): Promise<void> {
  await expect(page.getByText(PROCESSING_COMPLETE_RE).first()).toBeVisible({ timeout });
}

// Reads the runtime session id the app exposes on the status bar. The app keeps
// the id in memory only; we surface it via a data attribute for test assertions.
export async function readSessionId(page: Page): Promise<string> {
  const locator = page.getByTestId("session-id");
  await locator.waitFor({ state: "attached" });
  const value = await locator.getAttribute("data-session-id");
  if (!value) {
    throw new Error("session id was not present on the status bar");
  }
  return value;
}

// Selects files on the hidden upload input without opening a native dialog.
export async function chooseFiles(page: Page, files: string[]): Promise<void> {
  await page.getByTestId("upload-input").setInputFiles(files);
}
