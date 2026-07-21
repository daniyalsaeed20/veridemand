import { describe, expect, it } from "vitest";

import type { SessionLimits } from "../../contracts";
import { formatBytes, screenFiles } from "./clientChecks";

const LIMITS: SessionLimits = {
  max_files_per_session: 25,
  max_pages_per_session: 500,
  max_single_file_bytes: 1000,
  max_session_bytes: 10_000,
  max_filename_length: 20,
  supported_extensions: [".pdf", ".png", ".txt"],
};

function makeFile(name: string, size: number): File {
  const blob = new Blob([new Uint8Array(size)]);
  return new File([blob], name, { type: "application/octet-stream" });
}

describe("screenFiles", () => {
  it("accepts a supported file within limits", () => {
    const result = screenFiles([makeFile("a.png", 500)], LIMITS);
    expect(result.acceptable).toHaveLength(1);
    expect(result.rejected).toHaveLength(0);
  });

  it("rejects an unsupported extension", () => {
    const result = screenFiles([makeFile("a.exe", 100)], LIMITS);
    expect(result.acceptable).toHaveLength(0);
    expect(result.rejected[0].reason).toMatch(/Unsupported/);
  });

  it("rejects a file over the single-file limit", () => {
    const result = screenFiles([makeFile("a.pdf", 5000)], LIMITS);
    expect(result.rejected[0].reason).toMatch(/larger than/);
  });

  it("rejects an empty file", () => {
    const result = screenFiles([makeFile("a.pdf", 0)], LIMITS);
    expect(result.rejected[0].reason).toMatch(/empty/i);
  });

  it("rejects a file with no extension", () => {
    const result = screenFiles([makeFile("noext", 100)], LIMITS);
    expect(result.rejected[0].reason).toMatch(/Unsupported/);
  });

  it("partitions a mixed batch", () => {
    const result = screenFiles(
      [makeFile("ok.png", 100), makeFile("bad.exe", 100), makeFile("big.pdf", 5000)],
      LIMITS,
    );
    expect(result.acceptable).toHaveLength(1);
    expect(result.rejected).toHaveLength(2);
  });
});

describe("formatBytes", () => {
  it("formats byte magnitudes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(1_048_576)).toBe("1 MB");
    expect(formatBytes(104_857_600)).toBe("100 MB");
  });
});
