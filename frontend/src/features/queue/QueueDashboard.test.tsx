import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeDocument, makeSnapshot, renderWithClient } from "../../tests/testUtils";
import { QueueDashboard } from "./QueueDashboard";

const SESSION_ID = "ses_" + "0".repeat(32);

function snapshotWithDocuments() {
  return makeSnapshot({
    counts: {
      uploaded: 1,
      queued: 1,
      preparing: 0,
      ready_for_extraction: 1,
      cancelled: 0,
      failed: 0,
    },
    queue: { pending: 1, running: 0, active_document_id: null, active_job_id: null },
    documents: [
      makeDocument({ document_id: "doc_" + "1".repeat(32), status: "uploaded" }),
      makeDocument({
        document_id: "doc_" + "2".repeat(32),
        status: "queued",
        queue_position: 1,
      }),
      makeDocument({
        document_id: "doc_" + "3".repeat(32),
        status: "ready_for_extraction",
      }),
    ],
  });
}

describe("QueueDashboard", () => {
  it("shows status labels for documents", () => {
    renderWithClient(<QueueDashboard sessionId={SESSION_ID} snapshot={snapshotWithDocuments()} />);
    expect(screen.getByText("Uploaded")).toBeInTheDocument();
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("Ready for extraction")).toBeInTheDocument();
  });

  it("enables 'Process all uploaded' only when uploaded documents exist", () => {
    const { unmount } = renderWithClient(
      <QueueDashboard sessionId={SESSION_ID} snapshot={snapshotWithDocuments()} />,
    );
    expect(screen.getByRole("button", { name: /process all uploaded/i })).toBeEnabled();
    unmount();

    renderWithClient(<QueueDashboard sessionId={SESSION_ID} snapshot={makeSnapshot()} />);
    expect(screen.getByRole("button", { name: /process all uploaded/i })).toBeDisabled();
  });

  it("shows action eligibility per document state", () => {
    renderWithClient(<QueueDashboard sessionId={SESSION_ID} snapshot={snapshotWithDocuments()} />);
    // Uploaded -> Process; queued -> Cancel; all non-processing -> Remove.
    expect(screen.getAllByRole("button", { name: "Process" }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Remove" }).length).toBeGreaterThanOrEqual(1);
  });

  it("never implies extraction results are available (honest progress)", () => {
    renderWithClient(<QueueDashboard sessionId={SESSION_ID} snapshot={snapshotWithDocuments()} />);
    expect(screen.getByText(/no results are available yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/extraction complete/i)).toBeNull();
    expect(screen.getByText(/Extraction is not performed in this phase/i)).toBeInTheDocument();
  });

  it("renders an empty state with no documents", () => {
    renderWithClient(<QueueDashboard sessionId={SESSION_ID} snapshot={makeSnapshot()} />);
    expect(screen.getByText(/No documents yet/i)).toBeInTheDocument();
  });
});
