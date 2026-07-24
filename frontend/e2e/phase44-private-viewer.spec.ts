/**
 * Phase 4.4 private viewer acceptance against a running stack.
 * Skips automatically when opaque private PDFs are absent (CI-safe).
 */
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PRIV = path.join(ROOT, "fixtures", "private");

const FILES = [
  { label: "private_scan_001", file: path.join(PRIV, "private_scan_001.pdf") },
  { label: "private_digital_001", file: path.join(PRIV, "private_digital_001.pdf") },
  { label: "private_mixed_001", file: path.join(PRIV, "private_mixed_001.pdf") },
];

const PRIVATE_READY = FILES.every((f) => fs.existsSync(f.file));

test.describe("Phase 4.4 private viewer acceptance", () => {
  test.skip(!PRIVATE_READY, "opaque private PDFs not present locally");

  test("renders three opaque documents nonblank with navigation", async ({ page }) => {
    test.setTimeout(600_000);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    await page.getByTestId("upload-input").setInputFiles(FILES.map((f) => f.file));
    await expect(page.getByText(/3 files? accepted/i)).toBeVisible({ timeout: 30_000 });

    await page.getByRole("button", { name: /process all uploaded/i }).click();

    for (const { label } of FILES) {
      await expect(page.getByText(label, { exact: false }).first()).toBeVisible({
        timeout: 30_000,
      });
    }

    const openButtons = page.getByRole("button", { name: /open canonical document/i });
    await expect(openButtons).toHaveCount(3, { timeout: 480_000 });
    await openButtons.nth(0).click();
    let canvas = page.getByRole("img", { name: /page 1 of/i });
    await expect(canvas).toBeVisible({ timeout: 30_000 });
    await expect(canvas).toHaveAttribute("data-render-status", "rendered", { timeout: 30_000 });

    const next = page.getByRole("button", { name: /next page/i });
    if (await next.isEnabled()) {
      await next.click();
      await expect(page.getByRole("img", { name: /page 2 of/i })).toHaveAttribute(
        "data-render-status",
        "rendered",
        { timeout: 20_000 },
      );
      await page.getByRole("button", { name: /previous page/i }).click();
    }
    await page.getByRole("button", { name: /zoom in/i }).click();
    await page.getByRole("button", { name: /fit page width/i }).click();
    await page.getByRole("button", { name: /rotate clockwise/i }).click();
    await expect(page.getByRole("img", { name: /page 1 of/i })).toHaveAttribute(
      "data-render-status",
      "rendered",
      { timeout: 20_000 },
    );

    if ((await openButtons.count()) >= 2) {
      await openButtons.nth(1).click();
      canvas = page.getByRole("img", { name: /page 1 of/i });
      await expect(canvas).toHaveAttribute("data-render-status", "rendered", { timeout: 30_000 });
      await openButtons.nth(0).click();
      await expect(page.getByRole("img", { name: /page 1 of/i })).toHaveAttribute(
        "data-render-status",
        "rendered",
        { timeout: 30_000 },
      );
    }

    await expect(page.getByRole("img", { name: /page .* of/i }).first()).toBeVisible();
  });
});
