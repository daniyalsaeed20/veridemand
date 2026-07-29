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

function meaningfulAnnouncement(snapshot: ProgressSnapshotInput): string {
  const parts: string[] = [];
  if (snapshot.status) {
    parts.push(`Status ${snapshot.status.replaceAll("_", " ")}`);
  }
  const docPage = snapshot.document_page_number ?? snapshot.active_page_number;
  const docTotal = snapshot.document_pages_total;
  if (docPage != null && docTotal != null) {
    parts.push(`Document page ${docPage} of ${docTotal}`);
  }
  if (snapshot.selected_page_index != null && snapshot.selected_pages_total != null) {
    const route = snapshot.current_route;
    if (route === "digital_native") {
      parts.push(`Native page ${snapshot.selected_page_index} of ${snapshot.selected_pages_total}`);
    } else if ((snapshot.full_ocr_pages_selected ?? 0) > 0 || route === "full_visual_ocr") {
      parts.push(
        `Selected OCR page ${snapshot.selected_page_index} of ${snapshot.selected_pages_total}`,
      );
    }
  }
  if (snapshot.current_operation) {
    parts.push(`Operation ${snapshot.current_operation.replaceAll("_", " ")}`);
  }
  return parts.join(". ");
}

export function ProcessingDetailsCard({ snapshot }: ProcessingDetailsCardProps) {
  const active = isProgressActive(snapshot.status);
  const now = useLiveProgressClock(active);
  const receivedAtRef = useRef(captureSnapshotReceivedAt());
  const lastVersionRef = useRef<number | null>(null);
  const lastAnnouncementRef = useRef("");

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
    snapshot.operation_id,
    snapshot.document_page_number,
  ]);

  const live = deriveLiveProgress(snapshot, {
    receivedAtMonotonic: receivedAtRef.current,
    nowMonotonic: now,
    active,
  });

  const routeLabel = snapshot.current_route
    ? (ROUTE_LABELS[snapshot.current_route] ?? snapshot.current_route)
    : null;

  const docPage = snapshot.document_page_number ?? snapshot.active_page_number;
  const docTotal = snapshot.document_pages_total;
  const selectedIndex = snapshot.selected_page_index ?? snapshot.visual_page_index;
  const selectedTotal =
    snapshot.selected_pages_total ?? snapshot.visual_pages_total ?? snapshot.pages_total;
  const announcement = meaningfulAnnouncement(snapshot);
  if (announcement && announcement !== lastAnnouncementRef.current) {
    lastAnnouncementRef.current = announcement;
  }

  const selectedLabel =
    snapshot.current_route === "digital_native"
      ? "Native page"
      : (snapshot.full_ocr_pages_selected ?? 0) > 0 || snapshot.current_route === "full_visual_ocr"
        ? "Selected OCR page"
        : "Selected page";

  return (
    <Stack spacing={0.75}>
      <Typography
        component="div"
        role="status"
        aria-live="polite"
        aria-atomic="true"
        sx={{
          position: "absolute",
          width: 1,
          height: 1,
          overflow: "hidden",
          clip: "rect(0 0 0 0)",
        }}
      >
        {lastAnnouncementRef.current}
      </Typography>
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
      {docPage != null || docTotal != null ? (
        <Typography variant="body2">
          Document page {docPage ?? "—"}
          {docTotal != null ? ` of ${docTotal}` : ""}
        </Typography>
      ) : null}
      {selectedIndex != null && selectedTotal != null && selectedTotal > 0 ? (
        <Typography variant="body2">
          {selectedLabel} {selectedIndex} of {selectedTotal}
        </Typography>
      ) : null}
      <Typography variant="body2">
        Document pages completed: {snapshot.pages_completed ?? "—"}
        {docTotal != null ? ` of ${docTotal}` : ""}
      </Typography>
      {(snapshot.full_ocr_pages_selected ?? 0) > 0 ? (
        <Typography variant="body2">
          Selected OCR pages completed: {snapshot.full_ocr_pages_completed ?? 0} · Selected OCR
          pages remaining: {snapshot.full_ocr_pages_remaining ?? "—"}
        </Typography>
      ) : null}
      {routeLabel ? <Typography variant="body2">Current route: {routeLabel}</Typography> : null}
      {snapshot.current_operation ? (
        <Typography variant="body2">
          Current operation: {snapshot.current_operation.replaceAll("_", " ")}
        </Typography>
      ) : null}
      <Typography variant="body2">Batch elapsed: {live.batchElapsedLabel}</Typography>
      <Typography variant="body2">Current document elapsed: {live.documentElapsedLabel}</Typography>
      <Typography variant="body2">Current phase elapsed: {live.phaseElapsedLabel}</Typography>
      <Typography variant="body2">Current page elapsed: {live.pageElapsedLabel}</Typography>
      <Typography variant="body2">
        Current operation elapsed: {live.operationElapsedLabel}
      </Typography>
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
      <Typography variant="body2">
        Estimated current document remaining: {live.eta.label}
      </Typography>
      <Typography variant="body2">
        Estimated entire batch remaining: {live.batchEta.label}
      </Typography>
      {snapshot.estimate_confidence ? (
        <Typography variant="body2">
          Estimate confidence:{" "}
          {snapshot.estimate_confidence.charAt(0).toUpperCase() +
            snapshot.estimate_confidence.slice(1)}
          {snapshot.current_route ? " (based on current routing)" : ""}
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
