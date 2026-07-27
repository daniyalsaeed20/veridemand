import { Stack, Typography } from "@mui/material";
import { useEffect, useRef } from "react";

import {
  captureSnapshotReceivedAt,
  deriveLiveProgress,
  isProgressActive,
  type ProgressSnapshotInput,
} from "./deriveLiveProgress";
import { formatDuration } from "./formatDuration";
import { PageRouteBreakdown } from "./PageRouteBreakdown";
import { ProcessingTimeline } from "./ProcessingTimeline";
import { useLiveProgressClock } from "./useLiveProgressClock";

interface ProcessingDetailsCardProps {
  readonly snapshot: ProgressSnapshotInput & {
    readonly stage_timeline?: readonly Record<string, unknown>[] | null;
  };
}

const ROUTE_LABELS: Record<string, string> = {
  digital_native: "Digital native text",
  embedded_ocr_verified: "Embedded OCR verified",
  embedded_ocr_targeted_repair: "Targeted region repair",
  full_visual_ocr: "Full visual OCR",
  visual_no_text: "No visual text",
};

function phaseLabel(phase: string | null | undefined): string {
  if (!phase) return "—";
  if (phase === "visual_ocr") return "Visual OCR";
  if (phase === "native_trust") return "Native inspection";
  if (phase === "canonicalisation") return "Canonicalisation";
  return phase.replaceAll("_", " ");
}

export function ProcessingDetailsCard({ snapshot }: ProcessingDetailsCardProps) {
  const active = isProgressActive(snapshot.status);
  const now = useLiveProgressClock(active);
  const receivedAtRef = useRef(captureSnapshotReceivedAt());
  const lastVersionRef = useRef<number | null>(null);

  useEffect(() => {
    const version = snapshot.progress_version ?? null;
    if (version !== lastVersionRef.current) {
      lastVersionRef.current = version;
      receivedAtRef.current = captureSnapshotReceivedAt();
    }
  }, [
    snapshot.progress_version,
    snapshot.document_elapsed_seconds,
    snapshot.estimated_document_remaining_seconds,
    snapshot.estimate_status,
  ]);

  const live = deriveLiveProgress(snapshot, {
    receivedAtMonotonic: receivedAtRef.current,
    nowMonotonic: now,
    active,
  });

  const routeLabel = snapshot.current_route
    ? (ROUTE_LABELS[snapshot.current_route] ?? snapshot.current_route)
    : null;

  return (
    <Stack spacing={0.75} aria-live="polite" aria-atomic="false">
      <Typography variant="body2">
        Overall progress:{" "}
        {snapshot.progress_percent != null ? `${snapshot.progress_percent.toFixed(1)}%` : "—"}
      </Typography>
      <Typography variant="body2">
        Current phase: {phaseLabel(snapshot.major_phase)}
        {snapshot.major_phase_percent != null
          ? ` — ${snapshot.major_phase_percent.toFixed(1)}%`
          : ""}
      </Typography>
      {(snapshot.active_page_number != null || snapshot.pages_total != null) && (
        <Typography variant="body2">
          Document page: {snapshot.active_page_number ?? "—"}
          {snapshot.pages_total != null ? ` of ${snapshot.pages_total}` : ""}
        </Typography>
      )}
      <Typography variant="body2">
        Pages completed: {snapshot.pages_completed ?? "—"} · Pages remaining:{" "}
        {snapshot.pages_remaining ?? "—"}
      </Typography>
      {routeLabel ? <Typography variant="body2">Current route: {routeLabel}</Typography> : null}
      {snapshot.current_operation ? (
        <Typography variant="body2">
          Current operation: {snapshot.current_operation.replaceAll("_", " ")}
        </Typography>
      ) : null}
      <Typography variant="body2">Current page elapsed: {live.pageElapsedLabel}</Typography>
      <Typography variant="body2">Total elapsed: {live.documentElapsedLabel}</Typography>
      {snapshot.average_full_ocr_page_seconds != null ? (
        <Typography variant="body2">
          Average full-OCR page: {formatDuration(snapshot.average_full_ocr_page_seconds)}
        </Typography>
      ) : null}
      {snapshot.pages_per_minute != null ? (
        <Typography variant="body2">
          Current throughput: {snapshot.pages_per_minute.toFixed(1)} OCR pages/minute
        </Typography>
      ) : null}
      <Typography variant="body2">Estimated document remaining: {live.eta.label}</Typography>
      {snapshot.estimate_confidence ? (
        <Typography variant="body2">
          Estimate confidence:{" "}
          {snapshot.estimate_confidence.charAt(0).toUpperCase() +
            snapshot.estimate_confidence.slice(1)}
        </Typography>
      ) : null}
      <PageRouteBreakdown snapshot={snapshot} />
      <ProcessingTimeline
        entries={[
          { id: "canonical", label: "Canonical PDF", done: true },
          { id: "native", label: "Native inspection", done: true },
          {
            id: "routes",
            label: "Page routes evaluated",
            done: (snapshot.pages_completed ?? 0) > 0,
          },
          {
            id: "ocr",
            label: "Full OCR",
            active: snapshot.current_route === "full_visual_ocr",
          },
        ]}
        stageTimeline={snapshot.stage_timeline}
      />
    </Stack>
  );
}
