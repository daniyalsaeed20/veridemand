import { expect, test } from "@playwright/test";

import { readSessionId } from "./utils";

test.describe("VeriDemand application shell", () => {
  test("loads, bootstraps a runtime session, and connects the live stream", async ({ page }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];

    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(message.text());
      }
    });
    page.on("pageerror", (error) => {
      pageErrors.push(error.message);
    });

    await page.goto("/");

    await expect(page.getByRole("heading", { name: "VeriDemand" })).toBeVisible();
    await expect(page.getByText(/runtime-only/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Documents & queue/ })).toBeVisible();

    // A session id must be present and the SSE stream must report Live.
    const sessionId = await readSessionId(page);
    expect(sessionId).toMatch(/^ses_[0-9a-f]{32}$/);
    await expect(page.getByText("Live", { exact: true })).toBeVisible();

    // The runtime workspace must never persist state in the browser.
    const storageCounts = await page.evaluate(() => ({
      local: window.localStorage.length,
      session: window.sessionStorage.length,
      cookie: document.cookie,
    }));
    expect(storageCounts).toEqual({ local: 0, session: 0, cookie: "" });

    expect(pageErrors, pageErrors.join(", ")).toEqual([]);
    expect(consoleErrors, consoleErrors.join(", ")).toEqual([]);
  });
});
