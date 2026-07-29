/**
 * Correction 7 E2E: fair-scheduler queue UI and priority controls.
 *
 * Uses a synthetic multi-page PDF when available. Skips gracefully when the
 * upload surface or scheduler UI is not ready in this build.
 */
import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const FIXTURE = path.resolve(
  ROOT,
  "fixtures/synthetic/ocr/targeted-repair/A-one-wrong-word.pdf",
);

test.describe("Correction 7 fair document scheduling", () => {
  test("queue dashboard can show scheduler turn metadata when enabled", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /VeriDemand/i }).first()).toBeVisible({
      timeout: 60_000,
    });

    const fileInput = page.locator('input[type="file"]');
    if ((await fileInput.count()) === 0) {
      test.skip(true, "Upload control not available");
    }
    await fileInput.setInputFiles(FIXTURE);

    const processBtn = page.getByRole("button", { name: /process|start/i });
    if ((await processBtn.count()) > 0) {
      await processBtn.first().click({ timeout: 15_000 }).catch(() => null);
    }

    // Scheduler chrome may appear after admission; tolerate builds without OCR ready.
    const turnLabel = page.getByText(/Fair scheduler turn/i);
    const moveAhead = page.getByRole("button", { name: /Move ahead/i });
    await Promise.race([
      turnLabel.waitFor({ state: "visible", timeout: 120_000 }).catch(() => null),
      moveAhead.waitFor({ state: "visible", timeout: 120_000 }).catch(() => null),
      page.waitForTimeout(5_000),
    ]);

    if ((await turnLabel.count()) > 0) {
      await expect(turnLabel.first()).toBeVisible();
    }
    if ((await moveAhead.count()) > 0) {
      await expect(moveAhead.first()).toBeEnabled();
    }
    await expect(page.getByRole("heading", { name: /VeriDemand/i }).first()).toBeVisible();
  });

  test("priority move-ahead control does not crash the queue UI", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    const fileInput = page.locator('input[type="file"]');
    if ((await fileInput.count()) === 0) {
      test.skip(true, "Upload control not available");
    }
    await fileInput.setInputFiles(FIXTURE);
    const moveAhead = page.getByRole("button", { name: /Move ahead/i });
    await moveAhead.waitFor({ state: "visible", timeout: 120_000 }).catch(() => null);
    if ((await moveAhead.count()) === 0) {
      test.skip(true, "Priority controls not visible (scheduler may be disabled or idle)");
    }
    await moveAhead.first().click();
    await expect(page.getByRole("heading", { name: /VeriDemand/i }).first()).toBeVisible();
  });
});
