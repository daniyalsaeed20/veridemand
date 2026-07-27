/** ETA display helpers. */

export type EtaDisplay =
  | { kind: "unavailable"; label: "Calculating estimate…" }
  | { kind: "recalculating"; label: "Recalculating estimate…" }
  | { kind: "available"; label: string; remainingSeconds: number };

export function formatEta(
  remainingSeconds: number | null | undefined,
  estimateStatus: string | null | undefined,
): EtaDisplay {
  if (
    estimateStatus === "unavailable" ||
    estimateStatus === "collecting_samples" ||
    remainingSeconds == null ||
    !Number.isFinite(remainingSeconds)
  ) {
    return { kind: "unavailable", label: "Calculating estimate…" };
  }
  if (estimateStatus === "recalculating" || remainingSeconds <= 0) {
    // Overdue or explicitly recalculating — never show "0 seconds remaining".
    return { kind: "recalculating", label: "Recalculating estimate…" };
  }
  const total = Math.floor(remainingSeconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  let label: string;
  if (hours > 0) {
    label = `about ${hours}h ${minutes}m`;
  } else if (minutes > 0) {
    label = `about ${minutes} minute${minutes === 1 ? "" : "s"}`;
  } else {
    label = `about ${secs} second${secs === 1 ? "" : "s"}`;
  }
  return { kind: "available", label, remainingSeconds: total };
}
