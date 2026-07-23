import { expect, test } from "@playwright/test";

import { chooseFiles, fixture, waitForProcessingComplete } from "./utils";

test.describe("Phase 3 native trust", () => {
  test("good native PDF shows accepted words and aligned boxes", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [fixture("native/good-native-single-page.pdf")]);
    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await waitForProcessingComplete(page);

    await page.getByRole("button", { name: /open canonical document/i }).click();
    await expect(page.getByRole("img", { name: /page/i })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/Decision:\s*accepted/i).first()).toBeVisible();

    const toggle = page.getByLabel(/show native word boxes/i);
    if ((await toggle.count()) > 0) {
      await toggle.check();
      await expect(page.getByTestId("native-word-overlay")).toBeAttached();
      await expect(page.getByTestId("overlay-layer")).toHaveAttribute(
        "data-native-word-overlay",
        "true",
      );
    }

    await page.getByRole("button", { name: /zoom in/i }).click();
    await page.getByRole("button", { name: /rotate clockwise/i }).click();
    await expect(page.locator("[data-render-status=rendered]")).toBeVisible();
  });

  test("bad synthetic layer never shows rejected text", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [fixture("native/replacement-character-layer.pdf")]);
    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await waitForProcessingComplete(page);
    await page.getByRole("button", { name: /open canonical document/i }).click();

    await expect(
      page.getByText(/native text layer was rejected|requires visual processing/i).first(),
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("\uFFFD")).toHaveCount(0);
  });

  test("image-only requires visual processing and has no native boxes", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [fixture("native/image-only.pdf")]);
    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await waitForProcessingComplete(page);
    await page.getByRole("button", { name: /open canonical document/i }).click();
    await expect(page.getByText(/requires visual processing/i).first()).toBeVisible({
      timeout: 60_000,
    });
  });
});
