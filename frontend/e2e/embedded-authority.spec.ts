import { expect, test } from "@playwright/test";

import { chooseFiles, fixture, waitForProcessingComplete } from "./utils";

test.describe("Correction 1 embedded authority invariants", () => {
  test("sparse embedded form does not finish as empty embedded authority", async ({ page }) => {
    test.setTimeout(300_000);
    await page.goto("/");
    await chooseFiles(page, [fixture("ocr/sparse-embedded-form-2page.pdf")]);
    await page.getByRole("button", { name: /process all uploaded/i }).click();
    await waitForProcessingComplete(page);

    await page.getByRole("button", { name: /open canonical document/i }).click();
    await expect(page.getByRole("img", { name: /page/i })).toBeVisible({ timeout: 120_000 });

    // Must not claim empty embedded authority (Pages 0/N + embedded_ocr_authority).
    const statusChip = page.getByTestId("visual-processing-status-chip");
    if ((await statusChip.count()) > 0) {
      const status = await statusChip.first().innerText();
      expect(status).not.toBe("not_required");
    }
    await expect(page.getByTestId("embedded-result-invalid")).toHaveCount(0);

    const sourceLabel = page.getByTestId("visual-source-label");
    if ((await sourceLabel.count()) > 0) {
      const label = await sourceLabel.first().innerText();
      // Either verified embedded with boxes, or printed visual OCR after fallback.
      expect(label).toMatch(/Verified embedded OCR|Printed visual OCR/i);
      if (/Verified embedded OCR/i.test(label)) {
        await expect(page.getByText(/Lines:\s*[1-9]/i)).toBeVisible();
      }
    }

    // Phase 3 vs Phase 4 decisions shown separately when panels are present.
    const phase3 = page.getByTestId("phase3-visual-agreement");
    if ((await phase3.count()) > 0) {
      await expect(phase3.first()).toContainText(/Phase 3 visual agreement: not evaluated/i);
    }

    const lineToggle = page.getByLabel(/show line boxes/i);
    const wordToggle = page.getByLabel(/show word boxes/i);
    if ((await lineToggle.count()) > 0 && !(await lineToggle.isDisabled())) {
      await lineToggle.check();
      await expect(page.getByTestId("ocr-overlay-layer")).toBeAttached();
    }
    if ((await wordToggle.count()) > 0 && !(await wordToggle.isDisabled())) {
      await wordToggle.check();
      await expect(page.getByTestId("ocr-overlay-layer")).toBeAttached();
    }

    await page.getByRole("button", { name: /zoom in/i }).click();
    await page.getByRole("button", { name: /rotate clockwise/i }).click();
    await expect(page.locator("[data-render-status=rendered]")).toBeVisible();
    await page.getByRole("button", { name: /rotate clockwise/i }).click();
    await page.getByRole("button", { name: /rotate clockwise/i }).click();
    await page.getByRole("button", { name: /rotate clockwise/i }).click();
    await expect(page.locator("[data-render-status=rendered]")).toBeVisible();
  });
});
