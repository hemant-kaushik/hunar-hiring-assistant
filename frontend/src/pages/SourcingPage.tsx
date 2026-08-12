import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { CallsTable } from "../components/CallsTable";
import { Label } from "../components/Label";
import { StatusPill, statusExplanation } from "../components/StatusPill";
import { useLiveCalls } from "../hooks";
import type { Call, Candidate, Job, PersonResult, SearchFilters, SearchResponse } from "../types";
import { isCallOver } from "../types";

const EXAMPLE_JD = `Senior Backend Engineer

We're hiring a Senior Backend Engineer for our platform team in Bengaluru.

You'll work with Python, FastAPI and PostgreSQL, deploying to AWS with Docker.
Experience with Kubernetes is a plus. 5+ years of experience preferred.`;

/**
 * Task 2: a job description goes in, people come out, and reaching them reuses
 * the same call pipeline as screening.
 *
 * Laid out as three visible steps rather than one long form, because the middle
 * step -- reviewing the filters the description produced -- is the one a
 * recruiter most often needs to correct.
 */
export default function SourcingPage() {
  const [jd, setJd] = useState("");
  const [filters, setFilters] = useState<SearchFilters | null>(null);
  const [matched, setMatched] = useState<string[]>([]);
  const [search, setSearch] = useState<SearchResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [imported, setImported] = useState(0);

  useEffect(() => {
    api
      .listJobs()
      .then((all) => {
        setJobs(all);
        setJobId((current) => current || all[0]?.id || "");
      })
      .catch((e) => setError(e.message));
  }, []);

  async function readJd() {
    setError(null);
    setBusy("parse");
    try {
      const parsed = await api.parseJd(jd);
      const { matched_terms, ...rest } = parsed;
      setFilters(rest);
      setMatched(matched_terms);
      setSearch(null);
      setSelected(new Set());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function runSearch() {
    if (!filters) return;
    setError(null);
    setBusy("search");
    try {
      setSearch(await api.searchPeople(filters));
      setSelected(new Set());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function addSelected() {
    if (!search || !jobId) return;
    setError(null);
    setBusy("import");
    try {
      const people = search.results.filter((p) => selected.has(p.external_id));
      const added = await api.importPeople(jobId, people);
      setImported((n) => n + added.length);
      setSelected(new Set());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <>
      <h1>Find candidates</h1>
      <p className="subtitle">
        Paste a job description, search for people who match, then have the assistant reach
        out. Their answers land on the same dashboard as everyone else's.
      </p>

      {error && <div className="banner err">{error}</div>}

      {/* ---- Step 1: the job description ---- */}
      <div className="panel">
        <h2>1. Describe the role</h2>
        <div className="field">
          <Label htmlFor="jd" required>
            Job description
          </Label>
          <textarea
            id="jd"
            rows={8}
            value={jd}
            onChange={(e) => setJd(e.target.value)}
            placeholder="Paste the full job description here…"
          />
        </div>
        <div className="row">
          <button className="primary" onClick={readJd} disabled={jd.trim().length < 10 || !!busy}>
            {busy === "parse" ? "Reading…" : "Read the description"}
          </button>
          <button type="button" onClick={() => setJd(EXAMPLE_JD)} disabled={!!busy}>
            Use an example
          </button>
        </div>
      </div>

      {/* ---- Step 2: what we'll search for ---- */}
      {filters && (
        <div className="panel">
          <h2>2. Check what we'll search for</h2>
          <p className="muted small" style={{ marginTop: -8 }}>
            {matched.length > 0
              ? `Picked out of the description: ${matched.slice(0, 8).join(", ")}.`
              : "Nothing recognisable was found — add what you're looking for below."}{" "}
            Edit anything that looks wrong before searching.
          </p>

          <div className="row" style={{ alignItems: "flex-start" }}>
            <ListField
              label="Job titles"
              values={filters.titles}
              onChange={(titles) => setFilters({ ...filters, titles })}
            />
            <ListField
              label="Skills"
              values={filters.skills}
              onChange={(skills) => setFilters({ ...filters, skills })}
            />
            <ListField
              label="Locations"
              values={filters.locations}
              onChange={(locations) => setFilters({ ...filters, locations })}
            />
            <div className="field" style={{ flex: "0 0 110px" }}>
              <Label htmlFor="limit">How many</Label>
              <input
                id="limit"
                type="number"
                min={1}
                max={25}
                value={filters.limit}
                onChange={(e) =>
                  setFilters({ ...filters, limit: Number(e.target.value) || 5 })
                }
              />
            </div>
          </div>
          <button className="primary" onClick={runSearch} disabled={!!busy}>
            {busy === "search" ? "Searching…" : "Find people"}
          </button>
        </div>
      )}

      {/* ---- Step 3: results ---- */}
      {search && (
        <div className="panel">
          <div className="spread">
            <h2>3. Choose who to contact</h2>
            <span className="muted small">
              {search.results.length} found · {search.provider_label}
            </span>
          </div>

          {search.notice && <div className="banner info">{search.notice}</div>}

          {search.results.length === 0 ? (
            <div className="empty">
              Nobody matched. Try removing a skill or widening the location.
            </div>
          ) : (
            <>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: 32 }} />
                      <th>Person</th>
                      <th>Experience</th>
                      <th>Skills</th>
                      <th>Contactable</th>
                    </tr>
                  </thead>
                  <tbody>
                    {search.results.map((p) => (
                      <tr key={p.external_id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selected.has(p.external_id)}
                            onChange={() => toggle(p.external_id)}
                            aria-label={`Select ${p.name}`}
                            style={{ width: "auto" }}
                          />
                        </td>
                        <td>
                          <strong>{p.name}</strong>
                          <div className="muted small">
                            {p.headline || [p.title, p.company].filter(Boolean).join(" at ")}
                          </div>
                          <div className="muted small">{p.location}</div>
                        </td>
                        <td className="small">
                          {p.experience_years ? `${p.experience_years} yrs` : "—"}
                        </td>
                        <td className="small" style={{ maxWidth: 240 }}>
                          {p.skills.slice(0, 5).join(", ")}
                        </td>
                        <td>
                          <ContactCell person={p} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="row" style={{ marginTop: 14, alignItems: "flex-end" }}>
                <div className="field" style={{ marginBottom: 0, minWidth: 220 }}>
                  <Label htmlFor="role">Add them to this role</Label>
                  <select id="role" value={jobId} onChange={(e) => setJobId(e.target.value)}>
                    {jobs.length === 0 && <option value="">No roles yet</option>}
                    {jobs.map((j) => (
                      <option key={j.id} value={j.id}>
                        {j.title}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  className="primary"
                  onClick={addSelected}
                  disabled={selected.size === 0 || !jobId || !!busy}
                >
                  {busy === "import"
                    ? "Adding…"
                    : `Add ${selected.size || ""} to shortlist`.replace("  ", " ")}
                </button>
                {jobs.length === 0 && (
                  <span className="muted small">Create a role under Screening first.</span>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ---- Step 4: reach out ---- */}
      {jobId && <Shortlist jobId={jobId} refreshKey={imported} onError={setError} />}
    </>
  );
}

function ContactCell({ person }: { person: PersonResult }) {
  if (person.phone) return <span className="pill ok">Phone available</span>;
  if (person.has_phone) {
    return (
      <span className="pill warn" title="The data provider holds a number but does not release it on this plan">
        Number withheld
      </span>
    );
  }
  return <span className="muted small">No number</span>;
}

/** Comma-separated editing keeps the markup simple and the values obvious. */
function ListField({
  label,
  values,
  onChange,
}: {
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  const id = `f-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <div className="field" style={{ flex: 1, minWidth: 160 }}>
      <Label htmlFor={id}>{label}</Label>
      <input
        id={id}
        value={values.join(", ")}
        onChange={(e) =>
          onChange(
            e.target.value
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean),
          )
        }
        placeholder="Comma separated"
      />
    </div>
  );
}

/**
 * The shortlist for a role: everyone sourced, whether they can be called yet,
 * and what came back when they were.
 */
function Shortlist({
  jobId,
  refreshKey,
  onError,
}: {
  jobId: string;
  refreshKey: number;
  onError: (msg: string) => void;
}) {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [calls, setCalls] = useState<Call[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadCandidates = useCallback(
    () =>
      api
        .listCandidates(jobId)
        .then((all) => setCandidates(all.filter((c) => c.source === "PDL"))),
    [jobId],
  );
  const loadCalls = useCallback(
    () => api.listCalls({ jobId, purpose: "OUTREACH" }).then(setCalls),
    [jobId],
  );

  useEffect(() => {
    loadCandidates().catch((e) => onError(e.message));
    loadCalls().catch(() => null);
  }, [loadCandidates, loadCalls, refreshKey, onError]);

  useLiveCalls(calls, loadCalls);

  async function startOutreach(candidate: Candidate) {
    setBusyId(candidate.id);
    setNotice(null);
    try {
      const call = await api.startCall(candidate.id, "OUTREACH");
      if (call.status === "SCHEDULED" || call.status === "NOT_STARTED") {
        setNotice(
          `The call to ${candidate.name} was accepted, but calls can only be placed ` +
            "between 8am and 9pm. It is queued and will go out in the next window.",
        );
      }
      await loadCalls();
    } catch (e) {
      const message = (e as Error).message;
      setNotice(message);
      onError(message);
    } finally {
      setBusyId(null);
    }
  }

  async function savePhone(candidate: Candidate, phone: string) {
    try {
      await api.updateCandidate(candidate.id, { phone });
      await loadCandidates();
    } catch (e) {
      onError((e as Error).message);
    }
  }

  if (candidates.length === 0) return null;

  const latest = new Map<string, Call>();
  for (const c of calls) if (!latest.has(c.candidate_id)) latest.set(c.candidate_id, c);

  return (
    <>
      <div className="panel">
        <div className="spread">
          <h2>4. Reach out</h2>
          <span className="muted small">{candidates.length} shortlisted</span>
        </div>
        <p className="muted small" style={{ marginTop: -8 }}>
          People found through a search never asked to be contacted, so calls are made one at
          a time, by you.
        </p>

        {notice && <div className="banner warn">{notice}</div>}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Person</th>
                <th>Phone</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => {
                const meta = c.source_metadata as Record<string, unknown>;
                const call = latest.get(c.id);
                const onCall = call ? !isCallOver(call) : false;
                return (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.name}</strong>
                      <div className="muted small">{String(meta.headline ?? "")}</div>
                    </td>
                    <td>
                      <PhoneCell candidate={c} onSave={(phone) => savePhone(c, phone)} />
                    </td>
                    <td className="small">
                      {call ? (
                        <>
                          <StatusPill status={call.status} />
                          <div className="muted small" style={{ marginTop: 4 }}>
                            {statusExplanation(call.status) ??
                              new Date(call.created_at).toLocaleString()}
                          </div>
                        </>
                      ) : (
                        <span className="muted">Not contacted</span>
                      )}
                    </td>
                    <td>
                      {/* A disabled button with only a tooltip reads as a dead
                          click. Say what is missing instead. */}
                      {!c.phone ? (
                        <span className="muted small">Add a number to call</span>
                      ) : (
                        <button
                          className="primary small"
                          disabled={busyId === c.id || onCall}
                          onClick={() => void startOutreach(c)}
                        >
                          {busyId === c.id
                            ? "Calling…"
                            : onCall
                              ? "On the call"
                              : call
                                ? "Call again"
                                : "Reach out"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {calls.length > 0 && (
        <div className="panel">
          <h2>What they said</h2>
          <CallsTable calls={calls} onRefreshed={loadCalls} />
        </div>
      )}
    </>
  );
}

function PhoneCell({
  candidate,
  onSave,
}: {
  candidate: Candidate;
  onSave: (phone: string) => void;
}) {
  const [value, setValue] = useState("");
  const withheld = Boolean(
    (candidate.source_metadata as Record<string, unknown>)?.phone_withheld,
  );

  if (candidate.phone) return <span className="small">{candidate.phone}</span>;

  return (
    <div>
      <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="98765 43210"
          aria-label={`Phone number for ${candidate.name}`}
          style={{ maxWidth: 150 }}
        />
        <button className="small" disabled={!value.trim()} onClick={() => onSave(value)}>
          Save
        </button>
      </div>
      {withheld && (
        <div className="hint">The data provider won't share this number on our plan.</div>
      )}
    </div>
  );
}
