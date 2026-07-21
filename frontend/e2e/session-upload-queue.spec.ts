import { expect, test } from "@playwright/test";

import { chooseFiles, fixture } from "./utils";

test.describe("Bulk upload and processing queue", () => {
  test("accepts several documents, queues them, and reaches ready for extraction", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    await chooseFiles(page, [
      fixture("valid_single_page.pdf"),
      fixture("valid.png"),
      fixture("valid_utf8.txt"),
    ]);

    // The upload result is reported per batch (no fake percentages).
    await expect(page.getByText(/3 files accepted/)).toBeVisible();
    await expect(page.getByText("valid_single_page.pdf")).toBeVisible();
    await expect(page.getByText("valid.png")).toBeVisible();
    await expect(page.getByText("valid_utf8.txt")).toBeVisible();

    // Queue everything and wait, event-driven, for readiness.
    await page.getByRole("button", { name: /process all uploaded/i }).click();

    await expect(page.getByText("Ready for extraction").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Ready:", { exact: false })).toBeVisible();

    // Honest progress: the UI must never claim extraction results exist.
    await expect(page.getByText(/no results are\s+available yet/i).first()).toBeVisible();
    await expect(page.getByText(/extraction complete/i)).toHaveCount(0);
  });

  test("reports server-side rejections alongside accepted files (partial batch)", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    await chooseFiles(page, [fixture("valid.png"), fixture("corrupt.pdf")]);

    await expect(page.getByText(/1 file accepted/)).toBeVisible();
    await expect(page.getByText("Some files were rejected")).toBeVisible();
    await expect(page.getByText("corrupt.pdf")).toBeVisible();
  });

  test("rejects unsupported files before contacting the backend", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Upload documents" })).toBeVisible();

    await chooseFiles(page, [fixture("unsupported.xyz")]);

    await expect(page.getByText("Some files were rejected")).toBeVisible();
    await expect(page.getByText("unsupported.xyz")).toBeVisible();
  });
});
