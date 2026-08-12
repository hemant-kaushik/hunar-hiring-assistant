import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { CallsTable } from "../components/CallsTable";
import { Label } from "../components/Label";
import { StatusPill } from "../components/StatusPill";
import { useLiveCalls } from "../hooks";
import type { Call, Candidate, Job } from "../types";
import { isCallOver } from "../types";

export default function JobDetailPage() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [calls, setCalls] = useState<Call[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadCandidates = useCallback(
    () => api.listCandidates(jobId).then(setCandidates),
    [jobId],
  );
  const loadCalls = useCallback(() => api.listCalls({ jobId }).then(setCalls), [jobId]);

  useEffect(() => {
    Promise.all([api.getJob(jobId).then(setJob), loadCandidates(), loadCalls()]).catch((e) =>
      setError(e.message),
    );
  }, [jobId, loadCandidates, loadCalls]);

  // Keeps the table moving on its own while a call is running.
  useLiveCalls(calls, loadCalls);

  async function startCall(candidate: Candidate) {
    setError(null);
    setBusyId(candidate.id);
    try {
      await api.startCall(candidate.id);
      await loadCalls();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  if (error && !job) return <div className="banner err">{error}</div>;
  if (!job) return <p className="muted">Loading…</p>;

  const latestByCandidate = new Map<string, Call>();
  for (const call of calls) {
    // `calls` is newest-first, so the first hit per candidate is the latest.
    if (!latestByCandidate.has(call.candidate_id)) latestByCandidate.set(call.candidate_id, call);
  }

  const liveCount = calls.filter((c) => !isCallOver(c)).length;

  return (
    <>
      <p className="small">
        <Link to="/jobs">← All roles</Link>
      </p>
      <div className="spread">
        <h1>{job.title}</h1>
        {liveCount > 0 && (
          <span className="pill live">
            {liveCount} call{liveCount === 1 ? "" : "s"} in progress
          </span>
        )}
      </div>
      <p className="subtitle">
        {[
          job.location,
          `${job.questions.length} question${job.questions.length === 1 ? "" : "s"}`,
          `Calls in ${titleCase(job.language)}`,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>

      {error && <div className="banner err">{error}</div>}

      <div className="panel">
        <h2>What the assistant asks</h2>
        <ol className="muted" style={{ margin: 0, paddingLeft: 20 }}>
          {job.questions.map((q) => (
            <li key={q.key}>{q.question}</li>
          ))}
        </ol>
      </div>

      <div className="panel">
        <div className="spread">
          <h2>Candidates</h2>
          <span className="muted small">{candidates.length} total</span>
        </div>
        <AddCandidate jobId={jobId} onAdded={loadCandidates} onError={setError} />

        {candidates.length === 0 ? (
          <div className="empty">Add a candidate above to start a screening call.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Latest call</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => {
                  const call = latestByCandidate.get(c.id);
                  const onCall = call ? !isCallOver(call) : false;
                  return (
                    <tr key={c.id}>
                      <td>
                        {c.name}
                        {c.email && <div className="muted small">{c.email}</div>}
                      </td>
                      <td>{c.phone}</td>
                      <td>
                        {call ? (
                          <StatusCell call={call} />
                        ) : (
                          <span className="muted">Not called yet</span>
                        )}
                      </td>
                      <td>
                        <button
                          className="primary small"
                          disabled={busyId === c.id || onCall}
                          onClick={() => startCall(c)}
                        >
                          {busyId === c.id
                            ? "Calling…"
                            : onCall
                              ? "On the call"
                              : call
                                ? "Call again"
                                : "Start screening call"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <h2>Answers</h2>
        <CallsTable calls={calls} questions={job.questions} onRefreshed={loadCalls} />
      </div>
    </>
  );
}

function StatusCell({ call }: { call: Call }) {
  return (
    <>
      <StatusPill status={call.status} />
      <div className="muted small" style={{ marginTop: 4 }}>
        {new Date(call.created_at).toLocaleString()}
        {call.duration_seconds ? ` · ${Math.round(call.duration_seconds)}s` : ""}
      </div>
    </>
  );
}

function AddCandidate({
  jobId,
  onAdded,
  onError,
}: {
  jobId: string;
  onAdded: () => void;
  onError: (msg: string) => void;
}) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createCandidate({ name, phone, email: email || null, job_id: jobId });
      setName("");
      setPhone("");
      setEmail("");
      onAdded();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await api.uploadCandidates(jobId, file);
      onAdded();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      e.target.value = "";
    }
  }

  return (
    <form onSubmit={submit} style={{ marginBottom: 18 }}>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="field" style={{ flex: 2, marginBottom: 0 }}>
          <Label htmlFor="cname" required>
            Name
          </Label>
          <input id="cname" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="field" style={{ flex: 2, marginBottom: 0 }}>
          <Label htmlFor="cphone" required>
            Phone number
          </Label>
          <input
            id="cphone"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="98765 43210"
            required
          />
          <div className="hint">Indian numbers can be typed without +91.</div>
        </div>
        <div className="field" style={{ flex: 2, marginBottom: 0 }}>
          <Label htmlFor="cemail">Email</Label>
          <input
            id="cemail"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <button className="primary" disabled={saving} style={{ marginTop: 22 }}>
          {saving ? "Adding…" : "Add"}
        </button>
      </div>
      <div className="row small muted" style={{ marginTop: 8 }}>
        <span>Adding a lot of people? Upload a spreadsheet with name, phone and email:</span>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={upload}
          style={{ width: "auto" }}
          aria-label="Upload a CSV of candidates"
        />
      </div>
    </form>
  );
}

function titleCase(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase();
}
