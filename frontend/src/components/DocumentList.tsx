import { useCallback, useMemo, useState } from "react";
import type { Document } from "../api/client";
import {
  CLASSIFICATION_OPTIONS,
  classificationLabel,
  confirmClassification,
  isViewable,
  reorderDocuments,
  saveClassification,
  sortDocuments,
  toggleExclude,
  toggleSecondaryEvidence,
} from "./documentClassification";

type Props = {
  sessionId: string;
  documents: Document[];
  busy: boolean;
  selectedDocId: string | null;
  onSelect: (id: string) => void;
  onDocumentsChange: (docs: Document[]) => void;
  onError: (message: string) => void;
  onRemove: (documentId: string) => void;
};

function statusLabel(doc: Document): string {
  if (doc.error_code) return `${doc.status} · ${doc.error_code}`;
  return doc.status;
}

export default function DocumentList({
  sessionId,
  documents,
  busy,
  selectedDocId,
  onSelect,
  onDocumentsChange,
  onError,
  onRemove,
}: Props) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [saveNote, setSaveNote] = useState<string | null>(null);

  const ordered = useMemo(() => sortDocuments(documents), [documents]);

  const patchLocal = useCallback(
    (updated: Document) => {
      onDocumentsChange(documents.map((d) => (d.id === updated.id ? updated : d)));
    },
    [documents, onDocumentsChange],
  );

  const handleReorder = useCallback(
    async (targetId: string, insertBeforeId: string | null) => {
      const ids = ordered.map((d) => d.id);
      const from = ids.indexOf(targetId);
      if (from < 0) return;
      ids.splice(from, 1);
      const to = insertBeforeId ? ids.indexOf(insertBeforeId) : ids.length;
      ids.splice(to < 0 ? ids.length : to, 0, targetId);
      try {
        const updated = await reorderDocuments(sessionId, ids);
        onDocumentsChange(
          documents
            .map((d) => updated.find((u) => u.id === d.id) ?? d)
            .sort((a, b) => {
              const ai = a.sequence_index ?? 9999;
              const bi = b.sequence_index ?? 9999;
              return ai - bi;
            }),
        );
        setSaveNote("Sequence saved.");
      } catch (err) {
        onError(err instanceof Error ? err.message : "Failed to save sequence");
      }
    },
    [documents, onDocumentsChange, onError, ordered, sessionId],
  );

  const moveByKeyboard = useCallback(
    (docId: string, direction: -1 | 1) => {
      const idx = ordered.findIndex((d) => d.id === docId);
      if (idx < 0) return;
      const swap = idx + direction;
      if (swap < 0 || swap >= ordered.length) return;
      const target = ordered[swap]!;
      void handleReorder(docId, direction > 0 ? target.id : (ordered[swap - 1]?.id ?? null));
    },
    [handleReorder, ordered],
  );

  return (
    <div className="doc-list">
      <h2>Documents</h2>
      {saveNote ? <p className="muted">{saveNote}</p> : null}
      <ul className="doc-sequence-list">
        {ordered.map((doc, index) => {
          const lowConfidence =
            doc.classification_confidence != null && doc.classification_confidence < 0.55;
          const isDemand = doc.classification === "existing_demand";
          const isTemplate = doc.classification === "template";
          const confirmed = doc.classification_reason?.startsWith("user-confirmed");
          return (
            <li
              key={doc.id}
              className={`doc-row${dragId === doc.id ? " doc-row-dragging" : ""}${lowConfidence ? " doc-row-ambiguous" : ""}`}
              draggable={!busy}
              onDragStart={() => setDragId(doc.id)}
              onDragEnd={() => setDragId(null)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (dragId && dragId !== doc.id) void handleReorder(dragId, doc.id);
                setDragId(null);
              }}
            >
              <span className="doc-seq" aria-label={`Sequence ${index + 1}`}>
                {doc.sequence_index != null ? doc.sequence_index + 1 : "—"}
              </span>
              <div className="doc-row-main">
                <button
                  type="button"
                  className={`doc-select${selectedDocId === doc.id ? " doc-select-active" : ""}`}
                  disabled={!isViewable(doc)}
                  onClick={() => onSelect(doc.id)}
                >
                  <strong>{doc.display_name}</strong>
                </button>
                <div className="doc-meta muted">
                  {doc.file_type} · {statusLabel(doc)}
                  {doc.page_count != null ? ` · ${doc.page_count} page(s)` : ""}
                  {doc.page_quality_warning_count
                    ? ` · ${doc.page_quality_warning_count} quality warning(s)`
                    : ""}
                </div>
                <div className="doc-classification">
                  <label className="label-inline">
                    Type
                    <select
                      value={doc.classification ?? ""}
                      disabled={busy || doc.status === "duplicate"}
                      onChange={(e) => {
                        void (async () => {
                          try {
                            const updated = await saveClassification(
                              sessionId,
                              doc.id,
                              e.target.value,
                            );
                            patchLocal(updated);
                            setSaveNote("Classification updated.");
                          } catch (err) {
                            onError(err instanceof Error ? err.message : "Update failed");
                          }
                        })();
                      }}
                    >
                      <option value="">— select —</option>
                      {CLASSIFICATION_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {doc.classification_confidence != null ? (
                    <span className="doc-confidence">
                      Confidence: {(doc.classification_confidence * 100).toFixed(0)}%
                    </span>
                  ) : null}
                  {confirmed ? <span className="doc-badge">Confirmed</span> : null}
                  {isTemplate ? <span className="doc-badge">Template</span> : null}
                </div>
                {doc.classification_reason ? (
                  <p className="doc-reason muted">{doc.classification_reason}</p>
                ) : null}
                {isDemand ? (
                  <p className="doc-warning" role="alert">
                    Existing demand — not authoritative evidence unless secondary source is enabled
                    below.
                  </p>
                ) : null}
                <div className="doc-actions">
                  <button
                    type="button"
                    className="btn btn-small"
                    disabled={busy || !doc.classification}
                    onClick={() => {
                      void (async () => {
                        try {
                          const updated = await confirmClassification(sessionId, doc.id);
                          patchLocal(updated);
                          setSaveNote("Classification confirmed.");
                        } catch (err) {
                          onError(err instanceof Error ? err.message : "Confirm failed");
                        }
                      })();
                    }}
                  >
                    Confirm type
                  </button>
                  <label className="label-inline">
                    <input
                      type="checkbox"
                      checked={doc.exclude_from_drafting}
                      disabled={busy}
                      onChange={(e) => {
                        void (async () => {
                          try {
                            const updated = await toggleExclude(
                              sessionId,
                              doc.id,
                              e.target.checked,
                            );
                            patchLocal(updated);
                          } catch (err) {
                            onError(err instanceof Error ? err.message : "Update failed");
                          }
                        })();
                      }}
                    />
                    Exclude from drafting
                  </label>
                  {isDemand ? (
                    <label className="label-inline">
                      <input
                        type="checkbox"
                        checked={doc.treat_as_secondary_evidence}
                        disabled={busy}
                        onChange={(e) => {
                          void (async () => {
                            try {
                              const updated = await toggleSecondaryEvidence(
                                sessionId,
                                doc.id,
                                e.target.checked,
                              );
                              patchLocal(updated);
                            } catch (err) {
                              onError(err instanceof Error ? err.message : "Update failed");
                            }
                          })();
                        }}
                      />
                      Enable as secondary comparison source
                    </label>
                  ) : null}
                  <button
                    type="button"
                    className="btn btn-small"
                    disabled={busy || index === 0}
                    aria-label="Move up"
                    onClick={() => moveByKeyboard(doc.id, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="btn btn-small"
                    disabled={busy || index === ordered.length - 1}
                    aria-label="Move down"
                    onClick={() => moveByKeyboard(doc.id, 1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="btn btn-small btn-danger"
                    disabled={busy}
                    aria-label={`Remove ${doc.display_name}`}
                    onClick={() => onRemove(doc.id)}
                  >
                    Remove
                  </button>
                </div>
                {doc.classification ? (
                  <span className="sr-only">
                    Proposed type: {classificationLabel(doc.classification)}
                  </span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
