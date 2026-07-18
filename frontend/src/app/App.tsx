import { useEffect, useState } from "react";
import { fetchHealth } from "../api/client";
import type { HealthResponse } from "../schemas/health";
import { useShellStore } from "../store/shellStore";

const FRONTEND_VERSION = "0.0.0-dev";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const error = useShellStore((s) => s.error);
  const setError = useShellStore((s) => s.setError);
  const clearError = useShellStore((s) => s.clearError);

  useEffect(() => {
    let cancelled = false;
    clearError();
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
  }, [clearError, setError]);

  return (
    <main className="shell">
      <h1 className="brand">VeriDemand</h1>
      <p className="lede">
        Demand-letter automation prototype — Phase 0 repository and contracts foundation.
      </p>
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
      {error ? <div className="error-banner">{error}</div> : null}
      <p className="muted">No document processing UI in Phase 0.</p>
    </main>
  );
}
