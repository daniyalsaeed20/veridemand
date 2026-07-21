// Preliminary, advisory client-side checks.
//
// These exist purely to give fast feedback before a network round-trip. The
// backend remains the sole authority: it re-validates every filename, extension,
// signature, structure and size limit. Never trust these results for security.

import type { SessionLimits } from "../../contracts";

export interface PreliminaryRejection {
  readonly file: File;
  readonly reason: string;
}

export interface PreliminaryResult {
  readonly acceptable: File[];
  readonly rejected: PreliminaryRejection[];
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  if (dot < 0 || dot === name.length - 1) {
    return "";
  }
  return name.slice(dot).toLowerCase();
}

export function screenFiles(files: readonly File[], limits: SessionLimits): PreliminaryResult {
  const acceptable: File[] = [];
  const rejected: PreliminaryRejection[] = [];
  const supported = new Set(limits.supported_extensions.map((ext) => ext.toLowerCase()));

  for (const file of files) {
    const extension = extensionOf(file.name);
    if (extension === "" || !supported.has(extension)) {
      rejected.push({
        file,
        reason: `Unsupported file type. Allowed: ${limits.supported_extensions.join(", ")}.`,
      });
      continue;
    }
    if (file.size > limits.max_single_file_bytes) {
      rejected.push({
        file,
        reason: `File is larger than the ${formatBytes(limits.max_single_file_bytes)} per-file limit.`,
      });
      continue;
    }
    if (file.size === 0) {
      rejected.push({ file, reason: "File is empty." });
      continue;
    }
    if (file.name.length > limits.max_filename_length) {
      rejected.push({
        file,
        reason: `Filename exceeds ${limits.max_filename_length} characters.`,
      });
      continue;
    }
    acceptable.push(file);
  }

  return { acceptable, rejected };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 || Number.isInteger(value) ? 0 : 1)} ${units[unitIndex]}`;
}
