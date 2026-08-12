import type { CallStatus } from "../types";

const TONE: Record<CallStatus, string> = {
  PENDING: "",
  SIMULATED: "warn",
  NOT_STARTED: "",
  SCHEDULED: "",
  INITIATED: "live",
  RINGING: "live",
  IN_PROGRESS: "live",
  COMPLETED: "ok",
  NOT_CONNECTED: "warn",
  CANCELLED: "warn",
  FAILED: "err",
};

const LABEL: Partial<Record<CallStatus, string>> = {
  SIMULATED: "Simulated",
  IN_PROGRESS: "On call",
  NOT_CONNECTED: "No answer",
};

export function StatusPill({ status }: { status: CallStatus }) {
  const label = LABEL[status] ?? status.charAt(0) + status.slice(1).toLowerCase().replace("_", " ");
  return <span className={`pill ${TONE[status]}`}>{label}</span>;
}
