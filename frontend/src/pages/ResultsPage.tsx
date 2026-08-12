import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { CallsTable } from "../components/CallsTable";
import { useLiveCalls } from "../hooks";
import type { Call } from "../types";

/**
 * Every call, across every role.
 *
 * Because calls are discriminated by purpose rather than split across tables,
 * the sourcing module's calls will appear here too once it exists.
 */
export default function ResultsPage() {
  const [calls, setCalls] = useState<Call[] | null>(null);
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      api
        .listCalls({ purpose: purpose || undefined })
        .then(setCalls)
        .catch((e) => setError(e.message)),
    [purpose],
  );

  useEffect(() => {
    load();
  }, [load]);

  useLiveCalls(calls ?? [], load);

  return (
    <>
      <h1>Results</h1>
      <p className="subtitle">Answers from every screening call, most recent first.</p>

      {error && <div className="banner err">{error}</div>}

      <div className="panel">
        <div className="row" style={{ marginBottom: 14 }}>
          <label htmlFor="purpose" style={{ marginBottom: 0 }}>
            Show
          </label>
          <select
            id="purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            style={{ width: "auto" }}
          >
            <option value="">All calls</option>
            <option value="SCREENING">Screening calls</option>
            <option value="OUTREACH">Outreach calls</option>
          </select>
        </div>
        {calls === null ? (
          <p className="muted">Loading…</p>
        ) : (
          <CallsTable calls={calls} showJob onRefreshed={load} />
        )}
      </div>
    </>
  );
}
