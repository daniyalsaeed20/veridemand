import { expect, test } from "@playwright/test";

import { chooseFiles, fixture, readSessionId } from "./utils";

type OcrState = "starting" | "ready" | "failed_retryable" | "failed_terminal" | "disabled";

function ocrBody(state: OcrState, attempt = 1) {
  const base = {
    attempt_id: `attempt-${attempt}`,
    attempt_number: attempt,
    attempt_started_at: new Date(Date.now() - 5000).toISOString(),
    last_transition_at: new Date().toISOString(),
    stage_count: 5,
    detector_status: "pending",
    recognizer_status: "pending",
    model_verification_status: "pending",
    retry_after_seconds: 1,
  };
  if (state === "starting") {
    return {
      ...base,
      state: "loading_recognizer",
      stage: "loading_recognizer",
      stage_index: 4,
      stage_label: "Loading recognizer",
      ready: false,
      retryable: false,
      error_code: null,
      user_message: "Printed OCR is starting",
      operator_hint: null,
      technical_detail: null,
    };
  }
  if (state === "ready") {
    return {
      ...base,
      state: "ready",
      stage: null,
      stage_index: null,
      stage_label: null,
      ready: true,
      retryable: false,
      error_code: null,
      user_message: "Printed OCR is ready",
      operator_hint: null,
      technical_detail: null,
      detector_status: "ready",
      recognizer_status: "ready",
      model_verification_status: "ready",
      retry_after_seconds: null,
    };
  }
  if (state === "failed_retryable") {
    return {
      ...base,
      state: "failed",
      stage: "loading_detector",
      stage_index: 3,
      stage_label: "Loading detector",
      ready: false,
      retryable: true,
      error_code: "ocr_dll_load_failed",
      user_message: "Printed OCR dependency failed to load.",
      operator_hint:
        "The current environment may contain conflicting Torch and Paddle libraries. Start VeriDemand using the OCR-only .venv-ocr environment, then retry OCR.",
      technical_detail: "OSError: shm.dll",
      detector_status: "failed",
    };
  }
  if (state === "failed_terminal") {
    return {
      ...base,
      state: "failed",
      stage: "verifying_models",
      stage_index: 2,
      stage_label: "Verifying model files",
      ready: false,
      retryable: false,
      error_code: "ocr_models_missing",
      user_message: "Printed OCR model files are missing or incomplete.",
      operator_hint:
        "Bootstrap local OCR models with the approved models:ocr:bootstrap command, then retry.",
      technical_detail: "models_missing",
      model_verification_status: "failed",
    };
  }
  return {
    ...base,
    state: "disabled",
    stage: null,
    stage_index: null,
    stage_label: null,
    ready: false,
    retryable: false,
    error_code: "ocr_disabled",
    user_message: "Printed OCR is disabled.",
    operator_hint: "Enable OCR in settings (OCR_ENABLED=true) if printed OCR is required.",
    technical_detail: null,
    detector_status: "not_applicable",
    recognizer_status: "not_applicable",
    model_verification_status: "not_applicable",
    retry_after_seconds: null,
  };
}

function readinessEnvelope(ocr: ReturnType<typeof ocrBody>, status: "ready" | "not_ready") {
  return {
    status,
    service: "veridemand-api",
    app_name: "VeriDemand",
    version: "0.1.0",
    application_version: "0.1.0",
    git_commit: "testcommit",
    process_id: 1,
    worker_generation: 1,
    configuration_profile: "development+ocr_on",
    timestamp: new Date().toISOString(),
    request_id: "req-e2e",
    checks: [
      {
        name: "paddle_ocr",
        status: status === "ready" ? "pass" : "fail",
        required: true,
        message: ocr.user_message,
      },
    ],
    ocr_runtime: ocr,
  };
}

test.describe("OCR readiness UX", () => {
  test("delayed successful OCR initialization shows progress then clears", async ({ page }) => {
    let ready = false;
    await page.route("**/health/ready", async (route) => {
      const body = ready
        ? readinessEnvelope(ocrBody("ready"), "ready")
        : readinessEnvelope(ocrBody("starting"), "not_ready");
      await route.fulfill({
        status: ready ? 200 : 503,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
      // Flip to ready after the first starting poll is observed.
      if (!ready) {
        ready = true;
      }
    });

    await page.goto("/");
    await expect(page.getByRole("status").getByText("Printed OCR is starting")).toBeVisible();
    await expect(page.getByText(/Loading recognizer/i)).toBeVisible();
    await expect(page.getByText(/Step 4 of 5/i)).toBeVisible();
    await expect(page.getByText(/starting or unavailable/i)).toHaveCount(0);
    await expect(page.getByRole("status").getByText("Printed OCR is ready")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("retryable failure then Retry OCR transitions without refresh", async ({ page }) => {
    let phase: "fail" | "starting" | "ready" = "fail";
    let retryHits = 0;

    await page.route("**/health/ready", async (route) => {
      const state =
        phase === "fail" ? "failed_retryable" : phase === "starting" ? "starting" : "ready";
      const body = readinessEnvelope(
        ocrBody(state, phase === "ready" ? 2 : 1),
        phase === "ready" ? "ready" : "not_ready",
      );
      await route.fulfill({
        status: phase === "ready" ? 200 : 503,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });
    await page.route("**/api/v1/runtime/ocr/retry", async (route) => {
      retryHits += 1;
      phase = "starting";
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          attempt_id: "attempt-2",
          state: "starting",
          stage: "checking_configuration",
          status_url: "/health/ready",
        }),
      });
      setTimeout(() => {
        phase = "ready";
      }, 300);
    });

    await page.goto("/");
    await expect(page.getByRole("alert").getByText("Printed OCR could not start")).toBeVisible();
    await expect(page.getByRole("alert").getByText(/dependency failed to load/i)).toBeVisible();
    await page.getByRole("button", { name: /Retry OCR/i }).click();
    expect(retryHits).toBe(1);
    await expect(page.getByRole("status").getByText("Printed OCR is starting")).toBeVisible();
    await expect(page.getByRole("status").getByText("Printed OCR is ready")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("terminal missing-model failure disables Retry OCR", async ({ page }) => {
    await page.route("**/health/ready", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify(readinessEnvelope(ocrBody("failed_terminal"), "not_ready")),
      });
    });
    await page.goto("/");
    await expect(page.getByRole("alert").getByText(/model files are missing/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /Retry OCR/i })).toHaveCount(0);
    await expect(page.getByText(/Retry OCR is unavailable/i)).toBeVisible();
  });

  test("duplicate Retry OCR clicks do not spam retries while starting", async ({ page }) => {
    let retryHits = 0;
    let phase: "fail" | "starting" = "fail";
    await page.route("**/health/ready", async (route) => {
      const state = phase === "fail" ? "failed_retryable" : "starting";
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify(readinessEnvelope(ocrBody(state), "not_ready")),
      });
    });
    await page.route("**/api/v1/runtime/ocr/retry", async (route) => {
      retryHits += 1;
      phase = "starting";
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          attempt_id: "attempt-2",
          state: "starting",
          stage: "loading_detector",
          status_url: "/health/ready",
        }),
      });
    });

    await page.goto("/");
    const retry = page.getByRole("button", { name: /Retry OCR/i });
    await retry.click();
    await expect(page.getByRole("status").getByText("Printed OCR is starting")).toBeVisible();
    await expect(page.getByRole("button", { name: /Retry OCR/i })).toHaveCount(0);
    expect(retryHits).toBe(1);
  });

  test("backend unreachable shows Check connection, not Retry OCR", async ({ page }) => {
    await page.route("**/health/ready", async (route) => {
      await route.abort("connectionfailed");
    });
    await page.goto("/");
    await expect(page.getByText("Backend connection unavailable")).toBeVisible();
    await expect(page.getByRole("button", { name: /Check connection/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Retry OCR/i })).toHaveCount(0);
  });

  test("session contents are preserved across OCR retry", async ({ page }) => {
    let phase: "fail" | "ready" = "fail";
    await page.route("**/health/ready", async (route) => {
      const body =
        phase === "ready"
          ? readinessEnvelope(ocrBody("ready", 2), "ready")
          : readinessEnvelope(ocrBody("failed_retryable"), "not_ready");
      await route.fulfill({
        status: phase === "ready" ? 200 : 503,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });
    await page.route("**/api/v1/runtime/ocr/retry", async (route) => {
      phase = "ready";
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          attempt_id: "attempt-2",
          state: "starting",
          stage: "checking_configuration",
          status_url: "/health/ready",
        }),
      });
    });

    await page.goto("/");
    await chooseFiles(page, [fixture("valid_single_page.pdf")]);
    await expect(page.getByText(/valid_single_page\.pdf/i).first()).toBeVisible();
    const sessionId = await readSessionId(page);
    await page.getByRole("button", { name: /Retry OCR/i }).click();
    await expect(page.getByRole("status").getByText("Printed OCR is ready")).toBeVisible({
      timeout: 15_000,
    });
    expect(await readSessionId(page)).toBe(sessionId);
    await expect(page.getByText(/valid_single_page\.pdf/i).first()).toBeVisible();
  });
});
