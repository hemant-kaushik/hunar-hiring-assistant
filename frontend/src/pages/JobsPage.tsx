import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { Label } from "../components/Label";
import type { Job, QuestionType, ScreeningQuestion } from "../types";

const LANGUAGES = [
  "ENGLISH",
  "HINDI",
  "TAMIL",
  "TELUGU",
  "KANNADA",
  "MARATHI",
  "MALAYALAM",
  "GUJARATI",
  "BENGALI",
];

// Hunar's voices. Shown by name only — which persona is behind each is not
// something a recruiter needs to reason about.
const VOICES = ["NEHA", "ROY", "ZOE", "SAM", "MIRA", "EESHA"];

const STARTER_QUESTIONS: ScreeningQuestion[] = [
  {
    key: "years_experience",
    question: "How many years of relevant experience do you have?",
    type: "number",
    options: [],
  },
  {
    key: "notice_period",
    question: "What is your notice period?",
    type: "choice",
    options: ["Immediate", "15 days", "30 days", "60+ days"],
  },
  {
    key: "expected_ctc",
    question: "What is your expected compensation?",
    type: "text",
    options: [],
  },
];

/**
 * Every question needs a short identifier behind the scenes — it becomes the
 * column the answer lands in. Derived from the question text so nobody has to
 * think about it.
 */
function slugify(question: string): string {
  const slug = question
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .split("_")
    .slice(0, 4)
    .join("_");
  return (/^[a-z]/.test(slug) ? slug : `q_${slug}`).slice(0, 64) || "question";
}

function uniqueKeys(questions: ScreeningQuestion[]): ScreeningQuestion[] {
  const seen = new Set<string>();
  return questions.map((q) => {
    const base = q.key?.trim() || slugify(q.question);
    let key = base;
    for (let n = 2; seen.has(key); n++) key = `${base}_${n}`;
    seen.add(key);
    return { ...q, key };
  });
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .listJobs()
      .then(setJobs)
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  return (
    <>
      <h1>Screening</h1>
      <p className="subtitle">
        Add a role and the questions you want candidates asked. An AI assistant calls
        each candidate, holds the conversation, and files their answers on your
        dashboard.
      </p>

      {error && <div className="banner err">{error}</div>}

      <div className="grid-2">
        <NewJobForm onCreated={load} />
        <div className="panel">
          <h2>Your roles</h2>
          {jobs === null ? (
            <p className="muted">Loading…</p>
          ) : jobs.length === 0 ? (
            <div className="empty">No roles yet. Add one to start screening.</div>
          ) : (
            <div className="card-list">
              {jobs.map((job) => (
                <Link key={job.id} to={`/jobs/${job.id}`} className="card">
                  <div className="spread">
                    <strong>{job.title}</strong>
                    <span className="pill">
                      {job.questions.length} question{job.questions.length === 1 ? "" : "s"}
                    </span>
                  </div>
                  <div className="muted small">
                    {[
                      job.location,
                      `${job.candidate_count} candidate${job.candidate_count === 1 ? "" : "s"}`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function NewJobForm({ onCreated }: { onCreated: () => void }) {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("ENGLISH");
  const [voice, setVoice] = useState("NEHA");
  const [questions, setQuestions] = useState<ScreeningQuestion[]>(STARTER_QUESTIONS);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (i: number, patch: Partial<ScreeningQuestion>) =>
    setQuestions((qs) => qs.map((q, idx) => (idx === i ? { ...q, ...patch } : q)));

  const addQuestion = () =>
    setQuestions((qs) => [...qs, { key: "", question: "", type: "text", options: [] }]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const cleaned = uniqueKeys(
      questions
        .filter((q) => q.question.trim().length > 2)
        .map((q) => ({
          ...q,
          key: "", // re-derived from the final question text
          question: q.question.trim(),
          options: q.type === "choice" ? q.options.map((o) => o.trim()).filter(Boolean) : [],
        })),
    );

    if (cleaned.length === 0) {
      setError("Add at least one question — this is what the assistant asks on the call.");
      return;
    }

    setSaving(true);
    try {
      const job = await api.createJob({
        title: title.trim(),
        location: location.trim(),
        description: description.trim(),
        language,
        voice_persona: voice,
        questions: cleaned,
      });
      onCreated();
      navigate(`/jobs/${job.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Add a role</h2>
      <p className="muted small" style={{ marginTop: -8 }}>
        Fields marked <span className="req">*</span> are required.
      </p>
      {error && <div className="banner err">{error}</div>}

      <div className="field">
        <Label htmlFor="title" required>
          Job title
        </Label>
        <input
          id="title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Backend Engineer"
          required
          minLength={2}
        />
      </div>

      <div className="field">
        <Label htmlFor="location">Location</Label>
        <input
          id="location"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Bengaluru"
        />
      </div>

      <div className="field">
        <Label htmlFor="description">About the role</Label>
        <textarea
          id="description"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="A short summary of the job. The assistant uses this to answer basic questions on the call."
        />
      </div>

      <div className="row">
        <div className="field" style={{ flex: 1 }}>
          <Label htmlFor="language">Call language</Label>
          <select id="language" value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {titleCase(l)}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ flex: 1 }}>
          <Label htmlFor="voice">Assistant voice</Label>
          <select id="voice" value={voice} onChange={(e) => setVoice(e.target.value)}>
            {VOICES.map((v) => (
              <option key={v} value={v}>
                {titleCase(v)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <h3>
        Questions to ask<span className="req">*</span>
      </h3>
      <p className="muted small" style={{ marginTop: -4 }}>
        Each answer becomes its own column on the results dashboard.
      </p>

      {questions.map((q, i) => (
        <div className="question-row" key={i}>
          <input
            value={q.question}
            onChange={(e) => update(i, { question: e.target.value })}
            placeholder="What should the assistant ask?"
            aria-label={`Question ${i + 1}`}
          />
          {q.type === "choice" && (
            <>
              <input
                style={{ marginTop: 8 }}
                value={q.options.join(", ")}
                onChange={(e) => update(i, { options: e.target.value.split(",") })}
                placeholder="Immediate, 15 days, 30 days"
                aria-label={`Suggested answers for question ${i + 1}`}
              />
              <div className="hint">
                Suggested answers, separated by commas. If the candidate says something
                different, their own words are recorded instead.
              </div>
            </>
          )}
          <div className="meta">
            <select
              value={q.type}
              onChange={(e) => update(i, { type: e.target.value as QuestionType })}
              aria-label={`Answer type for question ${i + 1}`}
            >
              <option value="text">Free text</option>
              <option value="number">Number</option>
              <option value="boolean">Yes / No</option>
              <option value="choice">Pick from a list</option>
            </select>
            <span style={{ flex: 1 }} />
            <button
              type="button"
              className="link"
              onClick={() => setQuestions((qs) => qs.filter((_, idx) => idx !== i))}
              aria-label={`Remove question ${i + 1}`}
            >
              Remove
            </button>
          </div>
        </div>
      ))}

      <div className="row" style={{ marginTop: 12 }}>
        <button type="button" onClick={addQuestion}>
          Add question
        </button>
        <button type="submit" className="primary" disabled={saving}>
          {saving ? "Saving…" : "Save role"}
        </button>
      </div>
    </form>
  );
}

function titleCase(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase();
}
