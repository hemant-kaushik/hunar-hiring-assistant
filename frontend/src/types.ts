export type QuestionType = "text" | "boolean" | "number" | "choice";

export interface ScreeningQuestion {
  key: string;
  question: string;
  type: QuestionType;
  options: string[];
}

export interface Job {
  id: string;
  title: string;
  description: string;
  location: string;
  questions: ScreeningQuestion[];
  hunar_agent_id: string | null;
  language: string;
  voice_persona: string;
  created_at: string;
  candidate_count: number;
}

export interface Candidate {
  id: string;
  job_id: string | null;
  name: string;
  phone: string;
  email: string | null;
  source: "MANUAL" | "CSV" | "PDL" | "APOLLO";
  source_metadata: Record<string, unknown>;
  created_at: string;
}

/** ---- Sourcing (Task 2) ---- */

export interface SearchFilters {
  titles: string[];
  skills: string[];
  locations: string[];
  seniority: string[];
  company_size?: string | null;
  limit: number;
}

export interface ParsedJD extends SearchFilters {
  matched_terms: string[];
}

export interface PersonResult {
  external_id: string;
  name: string;
  headline: string;
  title: string;
  company: string;
  location: string;
  skills: string[];
  linkedin_url: string | null;
  experience_years: number | null;
  phone: string | null;
  email: string | null;
  /** True with a null `phone` means the provider has a number but won't release it. */
  has_phone: boolean;
  has_email: boolean;
  raw: Record<string, unknown>;
}

export interface SearchResponse {
  results: PersonResult[];
  source: "pdl" | "sample";
  provider_label: string;
  notice: string | null;
  filters: SearchFilters;
}

export type CallStatus =
  | "PENDING"
  | "SIMULATED"
  | "NOT_STARTED"
  | "SCHEDULED"
  | "INITIATED"
  | "RINGING"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "NOT_CONNECTED"
  | "CANCELLED"
  | "FAILED";

export interface Call {
  id: string;
  request_id: string;
  hunar_call_id: string | null;
  purpose: "SCREENING" | "OUTREACH" | "ATTENDANCE_CHECKIN";
  status: CallStatus;
  candidate_id: string;
  job_id: string | null;
  result: Record<string, unknown> | null;
  recording_url: string | null;
  engagement_status: string | null;
  answered_by: string | null;
  call_ended_by: string | null;
  duration_seconds: number | null;
  retry_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  ended_at: string | null;
  candidate_name: string | null;
  candidate_phone: string | null;
  job_title: string | null;
}

export interface Health {
  status: string;
  hunar_configured: boolean;
  dry_run_calls: boolean;
  public_base_url: string;
  webhooks_reachable: boolean;
}

export const TERMINAL_STATUSES: CallStatus[] = [
  "COMPLETED",
  "NOT_CONNECTED",
  "CANCELLED",
  "FAILED",
  "SIMULATED",
];

/** The conversation itself is over — nobody is on the phone any more. */
export function isCallOver(call: Call): boolean {
  return TERMINAL_STATUSES.includes(call.status);
}

/**
 * The call has ended but its answers have not landed yet.
 *
 * Hunar sends the status update and the extracted result as *separate*
 * webhooks, and the result trails the status by a few seconds. Treating a
 * COMPLETED call as finished stops the refresh exactly one beat before the
 * answers arrive — which is why results appeared only after a manual reload.
 */
export function isAwaitingResult(call: Call): boolean {
  if (!isCallOver(call) || call.result !== null) return false;
  // A call that failed or was never answered has no answers coming.
  if (call.status !== "COMPLETED" && call.status !== "SIMULATED") return false;
  return Date.now() - Date.parse(call.updated_at) < RESULT_GRACE_MS;
}

/**
 * A call the provider has queued for later, because it was requested outside
 * permitted calling hours. Nobody is being dialled, and nothing will change for
 * hours -- so it should neither look active nor be polled.
 */
export function isScheduledForLater(call: Call): boolean {
  return call.status === "SCHEDULED";
}

/**
 * Created, but not yet picked up by the provider.
 *
 * This is a doorway on the way to RINGING, not a resting state -- every call
 * passes through it in the second after it is placed. Excluding it from polling
 * froze the row at its initial status for the entire call, so the dashboard
 * only ever caught up on a manual reload. Bounded, so a call the provider never
 * accepted stops being polled instead of hammering the API forever.
 */
export function isStarting(call: Call): boolean {
  return (
    call.status === "NOT_STARTED" &&
    Date.now() - Date.parse(call.updated_at) < RESULT_GRACE_MS
  );
}

/** Keep refreshing while the call is live, or while its answers are still due. */
export function needsPolling(call: Call): boolean {
  if (isScheduledForLater(call)) return false;
  if (call.status === "NOT_STARTED") return isStarting(call);
  return !isCallOver(call) || isAwaitingResult(call);
}

/** How long to keep watching a finished call for its result webhook. */
const RESULT_GRACE_MS = 3 * 60 * 1000;
