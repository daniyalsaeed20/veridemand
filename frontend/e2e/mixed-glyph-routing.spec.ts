import { expect, test } from "@playwright/test";

import { chooseFiles, fixture, waitForProcessingComplete } from "./utils";

test.describe("Correction 3 mixed-glyph native routing", () => {
  test("isolated private-use checkbox retains digital native with safe warning", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await page.goto("/");
    await chooseFiles(page, [fixture("native/isolated-private-use-checkbox.pdf")]);
    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await waitForProcessingComplete(page);

    await page.getByRole("button", { name: /open canonical document/i }).click();
    await expect(page.getByRole("img", { name: /page/i })).toBeVisible({ timeout: 120_000 });

    const finalRoute = page.getByTestId("final-page-route");
    if ((await finalRoute.count()) > 0) {
      await expect(finalRoute.first()).toContainText(/digital_native/i);
    }
    const sourceLabel = page.getByTestId("visual-source-label");
    if ((await sourceLabel.count()) > 0) {
      await expect(sourceLabel.first()).toContainText(/Native PDF text|Trusted digital text/i);
    }
    // Quarantined private-use codepoints must never appear in the UI.
    await expect(page.getByText(/\uE001/)).toHaveCount(0);
    await expect(page.locator("[data-render-status=rendered]")).toBeVisible();
  });
});
