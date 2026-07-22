import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeDocument, makeSnapshot, renderWithClient } from "../../tests/testUtils";
import { useViewerStore } from "../viewer/viewerState";
import { DocumentCard } from "./DocumentCard";

vi.mock("./documentApi", () => ({
  cancelDocument: vi.fn(),
  removeDocument: vi.fn(),
}));
vi.mock("../session/sessionApi", () => ({
  processDocuments: vi.fn(),
  sessionPath: (id: string) => `/api/v1/sessions/${id}`,
}));

import { processDocuments } from "../session/sessionApi";
import { cancelDocument, removeDocument } from "./documentApi";

const mockedProcess = vi.mocked(processDocuments);
const mockedCancel = vi.mocked(cancelDocument);
const mockedRemove = vi.mocked(removeDocument);
const SESSION_ID = "ses_" + "0".repeat(32);
const DOC_ID = "doc_" + "1".repeat(32);

afterEach(() => {
  vi.clearAllMocks();
  useViewerStore.getState().selectDocument(null);
});

describe("DocumentCard", () => {
  it("queues an uploaded document via Process", async () => {
    mockedProcess.mockResolvedValue({ queued: [], ignored: [], session: makeSnapshot() });
    renderWithClient(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({ document_id: DOC_ID, status: "uploaded" })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Process" }));
    await waitFor(() => expect(mockedProcess).toHaveBeenCalledWith(SESSION_ID, [DOC_ID]));
  });

  it("cancels a queued document", async () => {
    mockedCancel.mockResolvedValue(makeDocument({ document_id: DOC_ID, status: "cancelled" }));
    renderWithClient(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({ document_id: DOC_ID, status: "queued", queue_position: 1 })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(mockedCancel).toHaveBeenCalledWith(SESSION_ID, DOC_ID));
  });

  it("removes a ready document", async () => {
    mockedRemove.mockResolvedValue(undefined);
    renderWithClient(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({ document_id: DOC_ID, status: "ready_for_extraction" })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(mockedRemove).toHaveBeenCalledWith(SESSION_ID, DOC_ID));
  });

  it("shows the queue position for queued documents", () => {
    renderWithClient(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({ document_id: DOC_ID, status: "queued", queue_position: 3 })}
      />,
    );
    expect(screen.getByText(/position 3/)).toBeInTheDocument();
  });

  it("does not offer Process for non-uploaded documents", () => {
    renderWithClient(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({ document_id: DOC_ID, status: "ready_for_extraction" })}
      />,
    );
    expect(screen.queryByRole("button", { name: "Process" })).toBeNull();
  });

  it("shows a Canonicalising chip and allows cancelling while canonicalising", () => {
    renderWithClient(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({ document_id: DOC_ID, status: "canonicalising" })}
      />,
    );
    expect(screen.getByText("Canonicalising")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it('offers "Open canonical document" only when canonical_view_available', () => {
    const { rerender } = renderWithClient(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({
          document_id: DOC_ID,
          status: "ready_for_extraction",
          canonical_view_available: false,
        })}
      />,
    );
    expect(screen.queryByRole("button", { name: /open canonical document/i })).toBeNull();

    rerender(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({
          document_id: DOC_ID,
          status: "ready_for_extraction",
          canonical_status: "ready",
          canonicalisation_method: "original_pdf",
          canonical_view_available: true,
        })}
      />,
    );
    expect(screen.getByRole("button", { name: /open canonical document/i })).toBeInTheDocument();
    expect(screen.getByText(/Canonical document ready/i)).toBeInTheDocument();
  });

  it('selects the document in the viewer store when "Open canonical document" is clicked', () => {
    renderWithClient(
      <DocumentCard
        sessionId={SESSION_ID}
        document={makeDocument({
          document_id: DOC_ID,
          status: "ready_for_extraction",
          canonical_view_available: true,
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /open canonical document/i }));
    expect(useViewerStore.getState().selectedDocumentId).toBe(DOC_ID);
  });
});
