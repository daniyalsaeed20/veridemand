import { expect, test } from "@playwright/test";

import { chooseFiles, fixture } from "./utils";

// Runs against the "holds" backend, which applies a test-only admission delay so
// a job stays queued/preparing long enough to be cancelled deterministically.
test.describe("Queue cancellation", () => {
  test("cancels an in-flight document before it becomes ready", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    await chooseFiles(page, [fixture("valid_single_page.pdf")]);
    await expect(page.getByText("valid_single_page.pdf")).toBeVisible();

    await page.getByRole("button", { name: /process all uploaded/i }).click();

    // The document card exposes a Cancel action while queued or preparing.
    const cancelButton = page.getByRole("button", { name: "Cancel" });
    await expect(cancelButton).toBeVisible({ timeout: 10_000 });
    await cancelButton.click();

    await expect(page.getByText("Cancelled", { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Ready for extraction")).toHaveCount(0);
  });
});
