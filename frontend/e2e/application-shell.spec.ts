import { expect, test } from "@playwright/test";

test.describe("VeriDemand application shell", () => {
  test("loads, reaches the backend, and reports live and ready", async ({ page }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const failedHealthRequests: string[] = [];

    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(message.text());
      }
    });
    page.on("pageerror", (error) => {
      pageErrors.push(error.message);
    });
    page.on("response", (response) => {
      if (response.url().includes("/health/") && !response.ok()) {
        failedHealthRequests.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto("/");

    await expect(page.getByRole("heading", { name: "VeriDemand" })).toBeVisible();
    await expect(page.getByText(/runtime-only/i)).toBeVisible();
    await expect(page.getByText("Live", { exact: true })).toBeVisible();
    await expect(page.getByText("Ready", { exact: true })).toBeVisible();

    expect(failedHealthRequests, failedHealthRequests.join(", ")).toEqual([]);
    expect(pageErrors, pageErrors.join(", ")).toEqual([]);
    expect(consoleErrors, consoleErrors.join(", ")).toEqual([]);
  });
});
