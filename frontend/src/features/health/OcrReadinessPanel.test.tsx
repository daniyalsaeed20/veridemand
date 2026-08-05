import { ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { theme } from "../../app/theme";
import type { OcrRuntimeStatus, ReadinessResponse } from "../../contracts";
import { OcrReadinessPanel } from "./OcrReadinessPanel";
import { deriveOcrPanelMode } from "./ocrReadinessMode";

function renderWithProviders(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}>{ui}</ThemeProvider>
    </QueryClientProvider>,
  );
}

function makeOcr(overrides: Partial<OcrRuntimeStatus> = {}): OcrRuntimeStatus {
  return {
    state: "starting",
    stage: "loading_recognizer",
    stage_index: 4,
    stage_count: 5,
    stage_label: "Loading recognizer",
    attempt_id: "attempt-1",
    attempt_number: 1,
    attempt_started_at: new Date(Date.now() - 18_000).toISOString(),
    last_transition_at: new Date().toISOString(),
    ready: false,
    retryable: false,
    error_code: null,
    user_message: "Printed OCR is starting",
    operator_hint: null,
    technical_detail: null,
    retry_after_seconds: 1,
    detector_status: "ready",
    recognizer_status: "in_progress",
    model_verification_status: "ready",
    ...overrides,
  };
}

function makeReadiness(ocr: OcrRuntimeStatus | null): ReadinessResponse {
  return {
    status: ocr?.ready ? "ready" : "not_ready",
    service: "veridemand-api",
    app_name: "VeriDemand",
    version: "0.1.0",
    application_version: "0.1.0",
    git_commit: "abc1234",
    process_id: 1,
    worker_generation: 1,
    configuration_profile: "development+ocr_on",
    timestamp: new Date().toISOString(),
    request_id: "req-1",
    checks: [],
    ocr_runtime: ocr,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("OcrReadinessPanel", () => {
  it("shows starting progress with stage wording and hides Retry", () => {
    renderWithProviders(
      <OcrReadinessPanel
        readiness={makeReadiness(makeOcr())}
        readinessError={false}
        onCheckConnection={() => undefined}
      />,
    );
    expect(screen.getByText("Printed OCR is starting")).toBeInTheDocument();
    expect(screen.getByText(/Loading recognizer/i)).toBeInTheDocument();
    expect(screen.getByText(/Step 4 of 5/i)).toBeInTheDocument();
    expect(screen.getByText(/second/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/OCR startup progress/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry OCR/i })).toBeNull();
    expect(screen.queryByText(/starting or unavailable/i)).toBeNull();
  });

  it("shows retryable failure with reason, Retry OCR, and technical details", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 202,
      headers: { get: () => "req-1" },
      json: async () => ({
        attempt_id: "attempt-2",
        state: "starting",
        stage: "checking_configuration",
        status_url: "/health/ready",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn(async () => undefined) },
    } as unknown as Navigator);

    const ocr = makeOcr({
      state: "failed",
      stage: "loading_detector",
      ready: false,
      retryable: true,
      error_code: "ocr_dll_load_failed",
      user_message: "Printed OCR dependency failed to load.",
      operator_hint:
        "The current environment may contain conflicting Torch and Paddle libraries. Start VeriDemand using the OCR-only .venv-ocr environment, then retry OCR.",
      technical_detail: "OSError: shm.dll",
    });

    renderWithProviders(
      <OcrReadinessPanel
        readiness={makeReadiness(ocr)}
        readinessError={false}
        onCheckConnection={() => undefined}
      />,
    );

    expect(screen.getByText("Printed OCR could not start")).toBeInTheDocument();
    expect(screen.getByText(/dependency failed to load/i)).toBeInTheDocument();
    expect(screen.getByText(/Suggested action:/i)).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: /Retry OCR/i });
    expect(retry).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: /Show technical details/i }));
    expect(screen.getByText(/ocr_dll_load_failed/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Copy diagnostics/i }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled());
    fireEvent.click(retry);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.stringify(fetchMock.mock.calls)).toContain("/api/v1/runtime/ocr/retry");
  });

  it("hides Retry for non-retryable failures and shows exact cause", () => {
    const ocr = makeOcr({
      state: "failed",
      ready: false,
      retryable: false,
      error_code: "ocr_models_missing",
      user_message: "Printed OCR model files are missing or incomplete.",
      operator_hint:
        "Bootstrap local OCR models with the approved models:ocr:bootstrap command, then retry.",
    });
    renderWithProviders(
      <OcrReadinessPanel
        readiness={makeReadiness(ocr)}
        readinessError={false}
        onCheckConnection={() => undefined}
      />,
    );
    expect(screen.getByText(/model files are missing/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry OCR/i })).toBeNull();
    expect(screen.getByText(/Retry OCR is unavailable/i)).toBeInTheDocument();
  });

  it("shows Check connection when backend is unreachable", () => {
    const onCheck = vi.fn();
    renderWithProviders(
      <OcrReadinessPanel readiness={undefined} readinessError onCheckConnection={onCheck} />,
    );
    expect(screen.getByText("Backend connection unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry OCR/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Check connection/i }));
    expect(onCheck).toHaveBeenCalled();
  });

  it("shows disabled as a warning, not starting", () => {
    const ocr = makeOcr({
      state: "disabled",
      ready: false,
      retryable: false,
      error_code: "ocr_disabled",
      user_message: "Printed OCR is disabled.",
      stage: null,
      stage_index: null,
      stage_label: null,
    });
    renderWithProviders(
      <OcrReadinessPanel
        readiness={makeReadiness(ocr)}
        readinessError={false}
        onCheckConnection={() => undefined}
      />,
    );
    expect(screen.getByText("Printed OCR is disabled")).toBeInTheDocument();
    expect(screen.queryByText(/still starting/i)).toBeNull();
  });

  it("deriveOcrPanelMode covers ready and failed modes", () => {
    expect(deriveOcrPanelMode(undefined, true)).toBe("backend_unreachable");
    expect(deriveOcrPanelMode(makeReadiness(makeOcr({ state: "ready", ready: true })), false)).toBe(
      "ready_flash",
    );
    expect(
      deriveOcrPanelMode(
        makeReadiness(makeOcr({ state: "failed", ready: false, retryable: true })),
        false,
      ),
    ).toBe("failed_retryable");
  });
});
