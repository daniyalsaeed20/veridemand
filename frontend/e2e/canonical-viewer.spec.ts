import { expect, test } from "@playwright/test";

import { chooseFiles, fixture } from "./utils";

test.describe("Canonical viewer (Phase 2)", () => {
  test("opens a canonical PDF and keeps the synthetic overlay aligned", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    await chooseFiles(page, [fixture("valid_multi_page.pdf")]);
    await expect(page.getByText(/1 file accepted/)).toBeVisible();

    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await expect(page.getByText(/canonical document ready/i).first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText(/extraction has not started/i).first()).toBeVisible();

    await page.getByRole("button", { name: /open canonical document/i }).click();
    await expect(page.getByRole("img", { name: /page 1 of/i })).toBeVisible({ timeout: 20_000 });

    const overlay = page.locator("svg").filter({ hasText: /alignment|synthetic/i }).first();
    const overlayAlt = page.locator('[aria-label*="Alignment"], [data-testid="overlay-layer"]').first();
    await expect(overlay.or(overlayAlt).first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: /next page/i }).click();
    await expect(page.getByRole("img", { name: /page 2 of/i })).toBeVisible();

    await page.getByRole("button", { name: /zoom in/i }).click();
    await page.getByRole("button", { name: /fit page width/i }).click();
    await page.getByRole("button", { name: /rotate clockwise/i }).click();

    await expect(page.getByText(/extraction has not started/i).first()).toBeVisible();
    await expect(page.getByText(/extraction complete/i)).toHaveCount(0);
  });

  test("canonicalises supported image and text formats", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [
      fixture("valid.png"),
      fixture("valid.jpeg"),
      fixture("valid_utf8.txt"),
      fixture("valid.bmp"),
      fixture("valid.webp"),
    ]);
    await expect(page.getByText(/5 files accepted/)).toBeVisible();
    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await expect(page.getByText(/ready for extraction/i).first()).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("button", { name: /open canonical document/i }).first()).toBeEnabled();
  });
});
