import type {
  Call,
  Candidate,
  Health,
  Job,
  ParsedJD,
  PersonResult,
  ScreeningQuestion,
  SearchFilters,
  SearchResponse,
} from "./types";

/**
 * In dev this is empty and Vite proxies /api to the backend (see vite.config.ts).
 * In production it is the deployed backend's origin, injected at build time.
 */
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: init?.body instanceof FormData ? {} : { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("Could not reach the API. Is the backend running?", 0);
  }

  if (!res.ok) {
    throw new ApiError(await readError(res), res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/**
 * FastAPI reports errors as a string `detail`, or a list of them for 422s.
 *
 * Validation entries arrive as machine-shaped text — "Value error, ..." over a
 * field path like ["body", "phone"]. Reshaped here into a sentence, because
 * this string is shown to the person using the app.
 */
async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map(describeValidationError).join(" ");
    }
  } catch {
    /* fall through to the generic message */
  }
  return "Something went wrong. Please try again.";
}

function describeValidationError(d: {
  loc?: (string | number)[];
  msg?: string;
}): string {
  const field = (d.loc ?? []).filter((p) => p !== "body").join(" ");
  const message = (d.msg ?? "Invalid value").replace(/^Value error,\s*/i, "");
  if (!field) return capitalize(message);
  return `${capitalize(String(field).replace(/_/g, " "))}: ${message}`;
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export interface JobInput {
  title: string;
  description: string;
  location: string;
  questions: ScreeningQuestion[];
  language: string;
  voice_persona: string;
}

export const api = {
  health: () => request<Health>("/api/health"),

  listJobs: () => request<Job[]>("/api/jobs/"),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (body: JobInput) =>
    request<Job>("/api/jobs/", { method: "POST", body: JSON.stringify(body) }),
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: "DELETE" }),

  listCandidates: (jobId?: string) =>
    request<Candidate[]>(`/api/candidates/${jobId ? `?job_id=${jobId}` : ""}`),
  createCandidate: (body: {
    name: string;
    phone: string;
    email?: string | null;
    job_id: string;
  }) => request<Candidate>("/api/candidates/", { method: "POST", body: JSON.stringify(body) }),
  uploadCandidates: (jobId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Candidate[]>(`/api/candidates/upload?job_id=${jobId}`, {
      method: "POST",
      body: form,
    });
  },
  deleteCandidate: (id: string) => request<void>(`/api/candidates/${id}`, { method: "DELETE" }),

  updateCandidate: (id: string, body: { phone?: string; name?: string; email?: string }) =>
    request<Candidate>(`/api/candidates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // ---- Sourcing (Task 2) ----
  parseJd: (jobDescription: string, limit = 5) =>
    request<ParsedJD>("/api/sourcing/parse", {
      method: "POST",
      body: JSON.stringify({ job_description: jobDescription, limit }),
    }),
  searchPeople: (filters: SearchFilters) =>
    request<SearchResponse>("/api/sourcing/search", {
      method: "POST",
      body: JSON.stringify(filters),
    }),
  importPeople: (jobId: string, people: PersonResult[]) =>
    request<Candidate[]>("/api/sourcing/import", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId, people }),
    }),

  listCalls: (params: { jobId?: string; purpose?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.jobId) qs.set("job_id", params.jobId);
    if (params.purpose) qs.set("purpose", params.purpose);
    return request<Call[]>(`/api/calls/${qs.toString() ? `?${qs}` : ""}`);
  },
  startCall: (candidateId: string, purpose: "SCREENING" | "OUTREACH" = "SCREENING") =>
    request<Call>("/api/calls/", {
      method: "POST",
      body: JSON.stringify({ candidate_id: candidateId, purpose }),
    }),
  refreshCall: (id: string) => request<Call>(`/api/calls/${id}/refresh`, { method: "POST" }),
};
