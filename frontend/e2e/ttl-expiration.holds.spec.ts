import { expect, test } from "@playwright/test";

// Runs against the "holds" backend, configured with a short session TTL so the
// warning and expiry transitions happen within the test window.
test.describe("Session TTL expiration", () => {
  test("warns before expiry and then ends the session", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    // The expiring warning is driven by a server-sent event, not a client timer.
    await expect(page.getByText(/about to expire/i)).toBeVisible({ timeout: 20_000 });

    // Once past the deadline the runtime session is closed and files are gone.
    await expect(page.getByText("Session ended", { exact: true })).toBeVisible({
      timeout: 25_000,
    });
    await expect(page.getByText(/permanently removed/i)).toBeVisible();
  });
});
