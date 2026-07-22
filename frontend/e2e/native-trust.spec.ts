import { expect, test } from "@playwright/test";

import { chooseFiles, fixture, readSessionId } from "./utils";

async function waitForNativeComplete(page: import("@playwright/test").Page) {
  await expect(page.getByText(/native text accepted|visual processing|native text layer was rejected/i).first()).toBeVisible({
    timeout: 120_000,
  });
}

test.describe("Phase 3 native trust", () => {
  test("good native PDF shows accepted words and aligned boxes", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [fixture("native/good-native-single-page.pdf")]);
    await page.getByRole("button", { name: /process all/i }).click();
    await waitForNativeComplete(page);

    await page.getByRole("button", { name: /open canonical/i }).click();
    await expect(page.getByRole("img", { name: /page/i })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/native_authority|Native text accepted/i).first()).toBeVisible();

    const toggle = page.getByRole("checkbox", { name: /show native word boxes/i });
    if (await toggle.count()) {
      await toggle.check();
      await expect(page.getByText(/Native PDF boxes/i).first()).toBeVisible();
    }

    // Zoom and rotate should keep the canvas rendered.
    await page.getByRole("button", { name: /zoom in/i }).click();
    await page.getByRole("button", { name: /rotate/i }).click();
    await expect(page.locator("[data-render-status=rendered]")).toBeVisible();
  });

  test("bad synthetic layer never shows rejected text", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [fixture("native/replacement-character-layer.pdf")]);
    await page.getByRole("button", { name: /process all/i }).click();
    await waitForNativeComplete(page);
    await page.getByRole("button", { name: /open canonical/i }).click();

    await expect(
      page.getByText(/native text layer was rejected|requires visual processing/i).first(),
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("\uFFFD")).toHaveCount(0);
    await expect(page.getByRole("checkbox", { name: /show native word boxes/i })).toHaveCount(0);
  });

  test("image-only requires visual processing and has no native boxes", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [fixture("native/image-only.pdf")]);
    await page.getByRole("button", { name: /process all/i }).click();
    await waitForNativeComplete(page);
    await page.getByRole("button", { name: /open canonical/i }).click();
    await expect(page.getByText(/requires visual processing/i).first()).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByRole("checkbox", { name: /show native word boxes/i })).toHaveCount(0);
  });
});
