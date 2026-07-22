import { expect, test } from "@playwright/test";

import { chooseFiles, fixture } from "./utils";

test.describe("Canonical viewer (Phase 2)", () => {
  test("opens a canonical PDF and survives rapid navigation and zoom", async ({ page }) => {
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
    const canvas = page.getByRole("img", { name: /page 1 of/i });
    await expect(canvas).toBeVisible({ timeout: 20_000 });
    await expect(canvas).toHaveAttribute("data-render-status", "rendered", { timeout: 20_000 });

    // Overlay is a DEV coordinate-test tool; absent in normal user mode.
    await expect(page.getByTestId("overlay-layer")).toHaveCount(0);
    await expect(page.getByLabel(/coordinate-test alignment overlay/i)).toHaveCount(0);

    await page.getByRole("button", { name: /next page/i }).click();
    await page.getByRole("button", { name: /previous page/i }).click();
    await page.getByRole("button", { name: /next page/i }).click();
    await expect(page.getByRole("img", { name: /page 2 of/i })).toHaveAttribute(
      "data-render-status",
      "rendered",
      { timeout: 20_000 },
    );

    await page.getByRole("button", { name: /zoom in/i }).click();
    await page.getByRole("button", { name: /zoom in/i }).click();
    await page.getByRole("button", { name: /fit page width/i }).click();
    await page.getByRole("button", { name: /rotate clockwise/i }).click();
    await expect(page.getByRole("img", { name: /page 2 of/i })).toHaveAttribute(
      "data-render-status",
      "rendered",
      { timeout: 20_000 },
    );

    // valid_multi_page.pdf is intentionally blank (page-count fixture only).
    await expect(page.getByText(/extraction has not started/i).first()).toBeVisible();
    await expect(page.getByText(/extraction complete/i)).toHaveCount(0);
  });

  test("renders non-blank pixels for a contentful image page", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [fixture("valid.png")]);
    await expect(page.getByText(/1 file accepted/)).toBeVisible();
    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await expect(page.getByText(/canonical document ready/i).first()).toBeVisible({
      timeout: 30_000,
    });
    await page.getByRole("button", { name: /open canonical document/i }).click();
    const canvas = page.getByRole("img", { name: /page 1 of/i });
    await expect(canvas).toHaveAttribute("data-render-status", "rendered", { timeout: 20_000 });

    const blank = await canvas.evaluate((node) => {
      const el = node as HTMLCanvasElement;
      const context = el.getContext("2d", { willReadFrequently: true });
      if (!context || el.width < 1 || el.height < 1) {
        return true;
      }
      const { data } = context.getImageData(0, 0, el.width, el.height);
      let ink = 0;
      for (let i = 0; i < data.length; i += 16) {
        const r = data[i] ?? 0;
        const g = data[i + 1] ?? 0;
        const b = data[i + 2] ?? 0;
        const a = data[i + 3] ?? 0;
        if (a > 8 && (r < 245 || g < 245 || b < 245)) {
          ink += 1;
        }
      }
      return ink === 0;
    });
    expect(blank).toBe(false);
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
    await expect(
      page.getByRole("button", { name: /open canonical document/i }).first(),
    ).toBeEnabled();
  });
});
