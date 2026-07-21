import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeDocument, makeSnapshot, renderWithClient } from "../../tests/testUtils";
import { UploadPanel } from "./UploadPanel";

vi.mock("./uploadApi", () => ({ uploadDocuments: vi.fn() }));
import { uploadDocuments } from "./uploadApi";

const mockedUpload = vi.mocked(uploadDocuments);
const SESSION_ID = "ses_" + "0".repeat(32);
const LIMITS = makeSnapshot().limits;

function makeFile(name: string, size: number, type = "application/octet-stream"): File {
  return new File([new Blob([new Uint8Array(size)])], name, { type });
}

function selectFiles(files: File[]): void {
  const input = screen.getByTestId("upload-input") as HTMLInputElement;
  fireEvent.change(input, { target: { files } });
}

afterEach(() => {
  mockedUpload.mockReset();
});

describe("UploadPanel", () => {
  it("shows supported formats and per-file limits", () => {
    renderWithClient(<UploadPanel sessionId={SESSION_ID} limits={LIMITS} />);
    expect(screen.getByRole("heading", { name: "Upload documents" })).toBeInTheDocument();
    expect(screen.getByText(/Supported:/)).toHaveTextContent(".pdf");
  });

  it("uploads accepted files and reports acceptance", async () => {
    mockedUpload.mockResolvedValue({
      accepted: [makeDocument()],
      rejected: [],
      session: makeSnapshot({ counts: { ...makeSnapshot().counts, uploaded: 1 } }),
    });
    renderWithClient(<UploadPanel sessionId={SESSION_ID} limits={LIMITS} />);

    selectFiles([makeFile("a.png", 500, "image/png")]);

    await waitFor(() => expect(mockedUpload).toHaveBeenCalledTimes(1));
    expect(mockedUpload.mock.calls[0][1]).toHaveLength(1);
    expect(await screen.findByText(/1 file accepted/)).toBeInTheDocument();
  });

  it("rejects unsupported files client-side without calling the API", async () => {
    renderWithClient(<UploadPanel sessionId={SESSION_ID} limits={LIMITS} />);

    selectFiles([makeFile("a.exe", 100)]);

    expect(await screen.findByText(/Some files were rejected/)).toBeInTheDocument();
    expect(mockedUpload).not.toHaveBeenCalled();
  });

  it("surfaces server-side rejections", async () => {
    mockedUpload.mockResolvedValue({
      accepted: [],
      rejected: [
        {
          input_index: 0,
          display_filename: "broken.pdf",
          error_code: "upload_corrupt_file",
          message: "The PDF could not be read.",
          client_media_type: null,
          detected_format: null,
        },
      ],
      session: makeSnapshot(),
    });
    renderWithClient(<UploadPanel sessionId={SESSION_ID} limits={LIMITS} />);

    selectFiles([makeFile("broken.pdf", 500, "application/pdf")]);

    expect(await screen.findByText("broken.pdf")).toBeInTheDocument();
    expect(screen.getByText("The PDF could not be read.")).toBeInTheDocument();
  });

  it("disables interaction when disabled", () => {
    renderWithClient(<UploadPanel sessionId={SESSION_ID} limits={LIMITS} disabled />);
    const input = screen.getByTestId("upload-input") as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });
});
