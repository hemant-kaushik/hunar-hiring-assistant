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
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      api
        .listCalls()
        .then(setCalls)
        .catch((e) => setError(e.message)),
    [],
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
        {calls === null ? (
          <p className="muted">Loading…</p>
        ) : (
          <CallsTable calls={calls} showJob onRefreshed={load} />
        )}
      </div>
    </>
  );
}
