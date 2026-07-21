import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "../api/client";

const FRONTEND_VERSION = "0.0.0-dev";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  }, []);

  return (
    <main className="shell">
      <h1 className="brand">VeriDemand</h1>
      <p className="lede">Document extraction foundation reset.</p>

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
    </main>
  );
}
