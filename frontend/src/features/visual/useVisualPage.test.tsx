import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { useVisualPage } from "./useVisualPage";

vi.mock("./visualApi", () => ({
  getVisualPage: vi.fn(async (_s: string, _d: string, pageNumber: number) => ({
    page_number: pageNumber,
    status: "completed",
    source_mode: "visual_authority",
    line_count: 1,
    word_count: 1,
    visual_result_available: true,
  })),
}));

import { getVisualPage } from "./visualApi";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useVisualPage", () => {
  it("fetches only the selected page lazily", async () => {
    const { rerender, result } = renderHook(
      ({ page }) => useVisualPage("ses_test", "doc_test", page, true),
      { initialProps: { page: 1 }, wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getVisualPage).toHaveBeenCalledWith(
      "ses_test",
      "doc_test",
      1,
      expect.anything(),
      expect.objectContaining({ includeLines: true, includeWords: true }),
    );

    rerender({ page: 2 });
    await waitFor(() => expect(result.current.data?.page_number).toBe(2));
    expect(getVisualPage).toHaveBeenCalledWith(
      "ses_test",
      "doc_test",
      2,
      expect.anything(),
      expect.objectContaining({ includeLines: true }),
    );
    // Two discrete page fetches — no bulk all-pages call.
    expect(vi.mocked(getVisualPage).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("does not fetch when disabled", async () => {
    vi.mocked(getVisualPage).mockClear();
    renderHook(() => useVisualPage("ses_test", "doc_test", 1, false), { wrapper });
    expect(getVisualPage).not.toHaveBeenCalled();
  });
});
