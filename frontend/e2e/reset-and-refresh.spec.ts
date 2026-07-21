import { expect, test } from "@playwright/test";

import { chooseFiles, fixture, readSessionId } from "./utils";

test.describe("Reset and refresh lifecycle", () => {
  test("reset discards uploads and starts a fresh session", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();
    const firstId = await readSessionId(page);

    await chooseFiles(page, [fixture("valid_utf8.txt")]);
    await expect(page.getByText("valid_utf8.txt")).toBeVisible();

    await page.getByRole("button", { name: /reset session/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /reset session/i }).click();

    // A new session id must appear and the previous upload must be gone.
    await expect.poll(async () => readSessionId(page), { timeout: 15_000 }).not.toBe(firstId);
    await expect(page.getByText("valid_utf8.txt")).toHaveCount(0);
    await expect(page.getByText(/No documents yet/i)).toBeVisible();
  });

  test("refreshing the page creates a brand-new session and never uses storage", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();
    const firstId = await readSessionId(page);

    await page.reload();
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    await expect.poll(async () => readSessionId(page), { timeout: 15_000 }).not.toBe(firstId);

    const storageCounts = await page.evaluate(() => ({
      local: window.localStorage.length,
      session: window.sessionStorage.length,
      cookie: document.cookie,
    }));
    expect(storageCounts).toEqual({ local: 0, session: 0, cookie: "" });
  });
});
