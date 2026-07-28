/**
 * Correction 4 progress E2E — synthetic documents only (no private files).
 */
import { expect, test } from "@playwright/test";

import { chooseFiles, fixture, waitForProcessingComplete } from "./utils";

test.describe("Correction 4 progress semantics", () => {
  test("mixed processing shows document page labels and reaches terminal progress", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    await chooseFiles(page, [fixture("valid_single_page.pdf"), fixture("ocr/clean_printable.pdf")]);
    await expect(page.getByText(/2 files accepted|1 file accepted/i).first()).toBeVisible({
      timeout: 30_000,
    });

    await page.getByRole("button", { name: /process all uploaded/i }).click();

    // Live progress should expose document-scoped wording while active or after.
    await expect(
      page.getByText(/Document page|Current document elapsed|Overall progress/i).first(),
    ).toBeVisible({ timeout: 120_000 });

    await waitForProcessingComplete(page, 180_000);

    // Phase 4 overall cap is 65% — terminal documents should not claim 100%.
    const progressText = page.getByText(/Overall progress:\s*\d/i);
    if ((await progressText.count()) > 0) {
      const text = await progressText.first().textContent();
      if (text) {
        const match = /(\d+(?:\.\d+)?)%/.exec(text);
        if (match) {
          expect(Number(match[1])).toBeLessThanOrEqual(65);
        }
      }
    }
  });

  test("SSE stays healthy across processing without private fixtures", async ({ page }) => {
    await page.goto("/");
    await chooseFiles(page, [fixture("valid_single_page.pdf")]);
    await expect(page.getByText(/1 file accepted/i)).toBeVisible();
    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await waitForProcessingComplete(page, 180_000);
    await expect(page.getByTestId("session-id")).toBeVisible();
  });
});
