import { useEffect, useMemo, useState } from "react";
import { listFacts, listIssues, listSpans, type Fact, type FactListResponse } from "../api/client";

export type FactFocusTarget = {
  documentId: string;
  pageNumber: number;
  spanIds: string[];
};

type IssueRow = {
  id: string;
  issue_type: string;
  severity: string;
  title: string;
  explanation: string;
  fact_ids?: string[] | null;
};

type Props = {
  sessionId: string;
  refreshKey: number;
  onFocusFact: (target: FactFocusTarget) => void;
};

function categoryOf(factType: string): string {
  const i = factType.indexOf(".");
  return i === -1 ? "other" : factType.slice(0, i);
}

function statusClass(status: string): string {
  switch (status) {
    case "verified":
      return "fact-status-verified";
    case "needs_review":
      return "fact-status-review";
    case "conflicting":
      return "fact-status-conflict";
    case "rejected":
      return "fact-status-rejected";
    case "locked":
      return "fact-status-locked";
    default:
      return "fact-status-suggested";
  }
}

export default function FactsPanel({ sessionId, refreshKey, onFocusFact }: Props) {
  const [data, setData] = useState<FactListResponse | null>(null);
  const [issues, setIssues] = useState<IssueRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    void (async () => {
      try {
        const [factsResp, issuesResp] = await Promise.all([
          listFacts(sessionId),
          listIssues(sessionId),
        ]);
        if (cancelled) return;
        setData(factsResp);
        setIssues(
          (issuesResp as IssueRow[]).filter(
            (i) =>
              i.issue_type.startsWith("extraction.missing") ||
              i.issue_type.includes("conflict") ||
              i.issue_type === "extraction.missing_critical_fact",
          ),
        );
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load facts");
        }
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, refreshKey]);

  const grouped = useMemo(() => {
    const map = new Map<string, Fact[]>();
    for (const fact of data?.facts ?? []) {
      const cat = categoryOf(fact.fact_type);
      const list = map.get(cat) ?? [];
      list.push(fact);
      map.set(cat, list);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [data]);

  const onSelectFact = async (fact: Fact) => {
    setSelectedId(fact.id);
    const spanIds = fact.source_span_ids ?? [];
    const docId = fact.document_ids?.[0];
    const spanId = spanIds[0];
    if (!docId || !spanId) return;
    // Resolve page from first span by probing pages 1..N via listSpans is expensive;
    // ask backend spans: try sequential pages until found (small prototype docs).
    try {
      for (let page = 1; page <= 40; page += 1) {
        const spans = await listSpans(sessionId, docId, page);
        const hit = spans.find((s) => spanIds.includes(s.id));
        if (hit) {
          onFocusFact({
            documentId: docId,
            pageNumber: page,
            spanIds,
          });
          return;
        }
        if (spans.length === 0 && page > 3) {
          // likely past end
          break;
        }
      }
    } catch {
      /* navigation best-effort */
    }
  };

  return (
    <section className="facts-panel" aria-label="Facts">
      <header className="facts-header">
        <h2>Facts</h2>
        <p className="muted">
          Fact status is not OCR confidence. Suggested values require review before drafting.
        </p>
        {data ? (
          <p className="muted facts-counts">
            {Object.entries(data.counts_by_status)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" · ") || "No facts yet"}
          </p>
        ) : null}
      </header>

      {busy ? <p className="muted">Loading facts…</p> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      {issues.length > 0 ? (
        <div className="facts-issues">
          <h3>Conflicts & missing critical fields</h3>
          <ul>
            {issues.map((issue) => (
              <li key={issue.id}>
                <strong className={`issue-sev-${issue.severity}`}>{issue.severity}</strong>{" "}
                {issue.title}
                <div className="muted">{issue.explanation}</div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {grouped.length === 0 && !busy ? (
        <p className="muted">No deterministic facts yet. Process documents first.</p>
      ) : (
        grouped.map(([category, facts]) => (
          <div key={category} className="fact-group">
            <h3>{category}</h3>
            <ul>
              {facts.map((fact) => {
                const ambiguous = fact.description?.includes("classification:ambiguous");
                const secondary = fact.description?.includes("authority:secondary");
                return (
                  <li key={fact.id}>
                    <button
                      type="button"
                      className={`fact-item${selectedId === fact.id ? " fact-item-active" : ""}`}
                      onClick={() => void onSelectFact(fact)}
                    >
                      <div className="fact-item-top">
                        <code>{fact.fact_type}</code>
                        <span className={`fact-status ${statusClass(String(fact.status))}`}>
                          {String(fact.status)}
                        </span>
                      </div>
                      <div className="fact-value">
                        {fact.display_value ?? fact.normalized_value ?? fact.raw_value}
                      </div>
                      <div className="muted fact-meta">
                        raw: {fact.raw_value.slice(0, 80)}
                        {" · "}
                        sources: {fact.source_span_ids?.length ?? 0}
                        {" · "}
                        method: {(fact.extraction_methods ?? []).join(", ") || "—"}
                        {" · "}
                        provenance: {fact.provenance ?? "—"}
                        {ambiguous ? " · classification unconfirmed" : ""}
                        {secondary ? " · secondary source (not primary)" : ""}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}
