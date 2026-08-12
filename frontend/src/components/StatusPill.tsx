import type { CallStatus } from "../types";

const TONE: Record<CallStatus, string> = {
  PENDING: "",
  SIMULATED: "warn",
  NOT_STARTED: "warn",
  SCHEDULED: "warn",
  INITIATED: "live",
  RINGING: "live",
  IN_PROGRESS: "live",
  COMPLETED: "ok",
  NOT_CONNECTED: "warn",
  CANCELLED: "warn",
  FAILED: "err",
};

const LABEL: Partial<Record<CallStatus, string>> = {
  SIMULATED: "Practice",
  IN_PROGRESS: "On call",
  NOT_CONNECTED: "No answer",
  SCHEDULED: "Queued",
  NOT_STARTED: "Queued",
};

/**
 * Why a status might need explaining: a call requested outside calling hours is
 * queued by the provider rather than dialled, and "SCHEDULED" on its own reads
 * as though the button did nothing.
 */
const EXPLANATION: Partial<Record<CallStatus, string>> = {
  SCHEDULED: "Outside calling hours — will be placed after 8am",
  NOT_STARTED: "Outside calling hours — will be placed after 8am",
};

export function StatusPill({ status }: { status: CallStatus }) {
  const label = LABEL[status] ?? status.charAt(0) + status.slice(1).toLowerCase().replace("_", " ");
  return (
    <span className={`pill ${TONE[status]}`} title={EXPLANATION[status]}>
      {label}
    </span>
  );
}

export function statusExplanation(status: CallStatus): string | undefined {
  return EXPLANATION[status];
}
