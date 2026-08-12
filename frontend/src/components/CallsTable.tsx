import { useState } from "react";

import { api } from "../api";
import type { Call, ScreeningQuestion } from "../types";
import { isAwaitingResult, isCallOver } from "../types";
import { StatusPill } from "./StatusPill";

/**
 * The results dashboard.
 *
 * Columns come from the job's own questions, so whatever a recruiter asked is
 * what they get back as a column -- that is the payoff of extracting answers
 * through Hunar's `result_schema` instead of leaving them buried in a
 * transcript.
 */
export function CallsTable({
  calls,
  questions,
  onRefreshed,
  showJob = false,
}: {
  calls: Call[];
  questions?: ScreeningQuestion[];
  onRefreshed?: () => void;
  showJob?: boolean;
}) {
  // Union of the job's declared keys and anything actually returned, so a
  // schema edited after a call still shows that call's older answers.
  const answerKeys = Array.from(
    new Set([
      ...(questions ?? []).map((q) => q.key),
      ...calls.flatMap((c) => Object.keys(c.result ?? {})),
    ]),
  ).filter((k) => k !== "summary" && !k.startsWith("_"));

  const labels = new Map((questions ?? []).map((q) => [q.key, q.question]));

  if (calls.length === 0) {
    return <div className="empty">Answers appear here once a screening call has finished.</div>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Candidate</th>
            {showJob && <th>Role</th>}
            <th>Status</th>
            {answerKeys.map((key) => (
              <th key={key} title={labels.get(key) ?? key}>
                {prettify(key)}
              </th>
            ))}
            <th>Recording</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {calls.map((call) => (
            <CallRow
              key={call.id}
              call={call}
              answerKeys={answerKeys}
              showJob={showJob}
              onRefreshed={onRefreshed}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CallRow({
  call,
  answerKeys,
  showJob,
  onRefreshed,
}: {
  call: Call;
  answerKeys: string[];
  showJob: boolean;
  onRefreshed?: () => void;
}) {
  const [refreshing, setRefreshing] = useState(false);
  const summary = call.result?.summary;
  const simulated = call.result?._simulated === true;
  const pendingAnswers = isAwaitingResult(call);

  async function refresh() {
    setRefreshing(true);
    try {
      await api.refreshCall(call.id);
      onRefreshed?.();
    } catch {
      /* transient; the poller will try again */
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <tr>
      <td>
        <strong>{call.candidate_name ?? "—"}</strong>
        <div className="muted small">{call.candidate_phone}</div>
        {typeof summary === "string" && (
          <div className="small" style={{ marginTop: 4, maxWidth: 320 }}>
            {summary}
          </div>
        )}
      </td>
      {showJob && <td className="small">{call.job_title ?? "—"}</td>}
      <td>
        <StatusPill status={call.status} />
        <div className="muted small" style={{ marginTop: 4 }}>
          {new Date(call.created_at).toLocaleString()}
          {call.duration_seconds ? ` · ${Math.round(call.duration_seconds)}s` : ""}
        </div>
        {call.error_message && (
          <div className="small" style={{ color: "var(--err)" }}>
            {call.error_message}
          </div>
        )}
        {pendingAnswers && <div className="muted small">Writing up the answers…</div>}
        {simulated && <div className="muted small">Practice run</div>}
      </td>
      {answerKeys.map((key) => (
        <td key={key}>{renderAnswer(call.result?.[key])}</td>
      ))}
      <td>
        {call.recording_url ? (
          <audio controls preload="none" src={call.recording_url} />
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td>
        {/* The table updates itself while a call is running; this is only for
            the impatient, or if an update went missing. */}
        {!isCallOver(call) && call.hunar_call_id && (
          <button className="small" onClick={refresh} disabled={refreshing}>
            {refreshing ? "…" : "Check now"}
          </button>
        )}
      </td>
    </tr>
  );
}

/**
 * Placeholders the extractor writes when it has no answer. They are values, not
 * absences, so they reach us as ordinary strings and would otherwise be
 * displayed as shouty "NOT AVAILABLE" text in the middle of a table.
 */
const NO_ANSWER = new Set([
  "not available",
  "not_available",
  "n/a",
  "na",
  "not applicable",
  "unknown",
  "none",
  "null",
  "-",
]);

function renderAnswer(value: unknown) {
  const missing = <span className="muted">Not answered</span>;

  if (value === undefined || value === null || value === "") return missing;
  if (typeof value === "boolean") {
    return <span className={`pill ${value ? "ok" : "warn"}`}>{value ? "Yes" : "No"}</span>;
  }
  if (typeof value === "object") {
    return <span className="small">{JSON.stringify(value)}</span>;
  }

  const text = String(value).trim();
  if (!text || NO_ANSWER.has(text.toLowerCase())) return missing;
  return <>{text}</>;
}

function prettify(key: string): string {
  return key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}
