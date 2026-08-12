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

/** Keep refreshing while the call is live, or while its answers are still due. */
export function needsPolling(call: Call): boolean {
  return !isCallOver(call) || isAwaitingResult(call);
}

/** How long to keep watching a finished call for its result webhook. */
const RESULT_GRACE_MS = 3 * 60 * 1000;
