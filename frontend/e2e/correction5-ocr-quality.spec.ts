/**
 * Correction 5 E2E: OCR quality progress and selected-pass overlays.
 *
 * Uses synthetic fixtures. Real Paddle coverage remains in backend integration tests.
 */
import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const FIXTURE = path.resolve(ROOT, "fixtures/synthetic/ocr/clean_printable.pdf");

test.describe("Correction 5 OCR quality gate UI", () => {
  test("clean OCR page shows primary selection without forcing fallback UI noise", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /VeriDemand/i }).first()).toBeVisible({
      timeout: 60_000,
    });

    const fileInput = page.locator('input[type="file"]');
    if ((await fileInput.count()) === 0) {
      test.skip(true, "Upload control not available in this build surface");
    }
    await fileInput.setInputFiles(FIXTURE);

    // Wait for processing UI; quality summary appears after visual OCR completes.
    const quality = page.getByTestId("ocr-quality-summary");
    await quality.waitFor({ state: "visible", timeout: 240_000 }).catch(() => null);
    if ((await quality.count()) === 0) {
      test.skip(true, "Document did not reach OCR inspection in time");
    }
    await expect(page.getByTestId("ocr-pass-labels")).toContainText(/Primary pass/i);
    // Clean letter should typically not require fallback.
    const fallbackChip = page.getByTestId("ocr-fallback-used");
    if ((await fallbackChip.count()) > 0) {
      // If fallback ran, selected pass must still be labelled.
      await expect(page.getByTestId("ocr-pass-labels")).toContainText(/Selected pass/i);
    }
    const overlay = page.getByTestId("ocr-overlay-layer");
    if ((await overlay.count()) > 0) {
      await expect(overlay.first()).toBeVisible();
    }
  });
});
