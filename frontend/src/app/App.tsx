import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  createSession,
  deleteDocument,
  deleteSession,
  fetchHealth,
  uploadDocuments,
  type HealthResponse,
} from "../api/client";
import { useShellStore } from "../store/shellStore";

const FRONTEND_VERSION = "0.0.0-dev";
const ACCEPT =
  ".pdf,.docx,.jpg,.jpeg,.png,.tif,.tiff,application/pdf,image/jpeg,image/png,image/tiff,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const error = useShellStore((s) => s.error);
  const session = useShellStore((s) => s.session);
  const documents = useShellStore((s) => s.documents);
  const rejections = useShellStore((s) => s.rejections);
  const expired = useShellStore((s) => s.expired);
  const setError = useShellStore((s) => s.setError);
  const clearError = useShellStore((s) => s.clearError);
  const setSession = useShellStore((s) => s.setSession);
  const addDocuments = useShellStore((s) => s.addDocuments);
  const setRejections = useShellStore((s) => s.setRejections);
  const setExpired = useShellStore((s) => s.setExpired);
  const removeDocument = useShellStore((s) => s.removeDocument);
  const resetLocal = useShellStore((s) => s.resetLocal);

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((data) => {
        if (!cancelled) setHealth(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load backend health");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [setError]);

  const handleApiError = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError) {
        if (err.envelope?.error_code === "session_expired" || err.status === 410) {
          setExpired(true);
          setSession(null);
          setError(err.message);
          return;
        }
        if (err.envelope?.error_code === "session_not_found" || err.status === 404) {
          setExpired(true);
          setSession(null);
          setError(err.message);
          return;
        }
        setError(err.message);
        return;
      }
      setError(err instanceof Error ? err.message : "Unexpected error");
    },
    [setError, setExpired, setSession],
  );

  const startCase = useCallback(async () => {
    setBusy(true);
    clearError();
    try {
      if (session) {
        await deleteSession(session.id);
      }
      resetLocal();
      const created = await createSession();
      setSession(created);
    } catch (err) {
      handleApiError(err);
    } finally {
      setBusy(false);
    }
  }, [clearError, handleApiError, resetLocal, session, setSession]);

  const resetCase = useCallback(async () => {
    setBusy(true);
    clearError();
    try {
      if (session) {
        await deleteSession(session.id);
      }
      resetLocal();
      const created = await createSession();
      setSession(created);
    } catch (err) {
      handleApiError(err);
    } finally {
      setBusy(false);
    }
  }, [clearError, handleApiError, resetLocal, session, setSession]);

  const onFiles = useCallback(
    async (fileList: FileList | File[]) => {
      if (!session) {
        setError("Start a temporary case session before uploading.");
        return;
      }
      const files = Array.from(fileList);
      if (files.length === 0) return;
      setBusy(true);
      clearError();
      try {
        const batch = await uploadDocuments(session.id, files);
        addDocuments(batch.accepted);
        setRejections(batch.rejected);
      } catch (err) {
        handleApiError(err);
      } finally {
        setBusy(false);
      }
    },
    [addDocuments, clearError, handleApiError, session, setError, setRejections],
  );

  const onRemove = useCallback(
    async (documentId: string) => {
      if (!session) return;
      setBusy(true);
      try {
        await deleteDocument(session.id, documentId);
        removeDocument(documentId);
      } catch (err) {
        handleApiError(err);
      } finally {
        setBusy(false);
      }
    },
    [handleApiError, removeDocument, session],
  );

  return (
    <main className="shell">
      <div className="proto-banner" role="status">
        Temporary Prototype — not a substitute for attorney review.
      </div>

      <h1 className="brand">VeriDemand</h1>
      <p className="lede">
        Demand-letter automation prototype — Phase 1 temporary session and secure upload.
      </p>

      {session?.warning ? (
        <p className="session-warning" role="alert">
          {session.warning}
        </p>
      ) : null}

      {expired ? (
        <div className="expired-panel">
          <p>This temporary session has expired or is no longer available.</p>
          <p className="muted">Deleted session data cannot be recovered. Start a new case.</p>
          <button type="button" className="btn" disabled={busy} onClick={() => void startCase()}>
            Start a new case
          </button>
        </div>
      ) : null}

      {!session && !expired ? (
        <div className="actions">
          <button type="button" className="btn" disabled={busy} onClick={() => void startCase()}>
            Start temporary case
          </button>
        </div>
      ) : null}

      {session && !expired ? (
        <section className="workspace">
          <header className="workspace-header">
            <div>
              <div className="label">Session</div>
              <code className="mono">{session.id}</code>
            </div>
            <div>
              <div className="label">Status</div>
              <span>{session.status}</span>
            </div>
            <div>
              <div className="label">Expires</div>
              <span>{new Date(session.expires_at).toLocaleString()}</span>
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => void resetCase()}
            >
              Reset Case
            </button>
          </header>

          <div
            className={`dropzone${dragOver ? " dropzone-active" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              void onFiles(e.dataTransfer.files);
            }}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            role="button"
            tabIndex={0}
          >
            <p>Drop PDF, DOCX, JPG, PNG, or TIFF files here</p>
            <p className="muted">or click to select</p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => {
                if (e.target.files) void onFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {documents.length > 0 ? (
            <div className="doc-list">
              <h2>Accepted documents</h2>
              <ul>
                {documents.map((doc) => (
                  <li key={doc.id}>
                    <div>
                      <strong>{doc.display_name}</strong>
                      <span className="muted">
                        {" "}
                        · {doc.file_type} · {doc.status}
                        {doc.page_count != null ? ` · ${doc.page_count} page(s)` : ""}
                      </span>
                      {doc.status === "duplicate" ? (
                        <span className="dup-warn"> Exact duplicate of another upload.</span>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      className="btn btn-small"
                      disabled={busy}
                      onClick={() => void onRemove(doc.id)}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {rejections.length > 0 ? (
            <div className="reject-list">
              <h2>Rejected files</h2>
              <ul>
                {rejections.map((rej, i) => (
                  <li key={`${rej.display_name}-${i}`}>
                    <strong>{rej.display_name}</strong>
                    <span className="muted">
                      {" "}
                      · {rej.error_code}: {rej.message}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}

      <ul className="meta">
        <li>
          <span>Frontend version</span>
          <span>{FRONTEND_VERSION}</span>
        </li>
        <li>
          <span>Backend health</span>
          <span>{health?.status ?? "loading…"}</span>
        </li>
        <li>
          <span>Backend app version</span>
          <span>{health?.app_version ?? "—"}</span>
        </li>
        <li>
          <span>Contracts version</span>
          <span>{health?.contracts_version ?? "—"}</span>
        </li>
      </ul>
    </main>
  );
}
