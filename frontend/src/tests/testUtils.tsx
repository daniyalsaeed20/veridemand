import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

import type { SessionSnapshot } from "../features/viewer/viewerApi";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithClient(ui: ReactElement, client: QueryClient = createTestQueryClient()) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, ...render(ui, { wrapper }) };
}

// A controllable EventSource stand-in for jsdom (which has no EventSource).
export class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  private readonly listeners: Record<string, Array<(event: MessageEvent) => void>> = {};

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  static reset(): void {
    MockEventSource.instances = [];
  }

  static latest(): MockEventSource {
    const source = MockEventSource.instances.at(-1);
    if (!source) {
      throw new Error("No MockEventSource has been constructed.");
    }
    return source;
  }

  addEventListener(type: string, callback: (event: MessageEvent) => void): void {
    (this.listeners[type] ??= []).push(callback);
  }

  removeEventListener(type: string, callback: (event: MessageEvent) => void): void {
    this.listeners[type] = (this.listeners[type] ?? []).filter((cb) => cb !== callback);
  }

  close(): void {
    this.readyState = 2;
  }

  emitOpen(): void {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  emitError(): void {
    this.onerror?.(new Event("error"));
  }

  emit(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    for (const callback of this.listeners[type] ?? []) {
      callback(event);
    }
  }

  emitRaw(type: string, raw: string): void {
    const event = new MessageEvent(type, { data: raw });
    for (const callback of this.listeners[type] ?? []) {
      callback(event);
    }
  }
}

export function makeSnapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
  const now = new Date().toISOString();
  const base: SessionSnapshot = {
    session_id: "ses_" + "0".repeat(32),
    status: "accepting_uploads",
    created_at: now,
    last_activity_at: now,
    expires_at: new Date(Date.now() + 7_200_000).toISOString(),
    expiring: false,
    seconds_remaining: 7200,
    limits: {
      max_files_per_session: 25,
      max_pages_per_session: 500,
      max_single_file_bytes: 104_857_600,
      max_session_bytes: 524_288_000,
      max_filename_length: 255,
      supported_extensions: [".pdf", ".png", ".jpeg", ".txt", ".docx"],
    },
    runtime_warning: "Runtime-only: refreshing or resetting removes all data.",
    counts: {
      uploaded: 0,
      queued: 0,
      canonicalising: 0,
      ready_for_extraction: 0,
      inspecting_native: 0,
      extracting_native: 0,
      native_trust_complete: 0,
      cancelled: 0,
      failed: 0,
    },
    accepted_bytes: 0,
    known_pages: 0,
    unknown_page_documents: 0,
    queue: { pending: 0, running: 0, active_document_id: null, active_job_id: null },
    documents: [],
    jobs: [],
    recent_events: [],
  };
  return { ...base, ...overrides };
}

export function makeDocument(
  overrides: Partial<SessionSnapshot["documents"][number]> = {},
): SessionSnapshot["documents"][number] {
  return {
    document_id: "doc_" + "0".repeat(32),
    display_filename: "sample.png",
    extension: "png",
    format: "png",
    media_type: "image/png",
    size_bytes: 1024,
    sha256: "0".repeat(64),
    page_count: 1,
    page_count_status: "known",
    status: "uploaded",
    progress_percent: 5,
    result_available: false,
    extraction_performed: false,
    native_extraction_performed: false,
    native_result_available: false,
    visual_processing_required: false,
    document_source_policy: null,
    user_status_message: null,
    warning_count: 0,
    queue_position: null,
    active_job_id: null,
    created_at: new Date().toISOString(),
    canonical_status: null,
    canonicalisation_method: null,
    canonical_view_available: false,
    canonical_view_url: null,
    canonical_metadata_url: null,
    native_summary_url: null,
    ...overrides,
  };
}
