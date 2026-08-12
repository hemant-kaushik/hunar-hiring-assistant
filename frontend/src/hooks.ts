import { useEffect, useRef } from "react";

import { api } from "./api";
import type { Call } from "./types";
import { needsPolling } from "./types";

const POLL_MS = 3000;

/**
 * Keeps a list of calls up to date while anything is still happening.
 *
 * Webhooks from Hunar are what actually update the database; this pulls those
 * changes onto the screen so a live call visibly progresses without anyone
 * touching the page. It also asks the backend to re-read any in-flight call
 * straight from Hunar, which covers a webhook that was missed or could not be
 * delivered. Polling stops as soon as every call has finished and its answers
 * have arrived, so an idle dashboard makes no requests at all.
 */
export function useLiveCalls(calls: Call[], reload: () => Promise<unknown>) {
  const callsRef = useRef(calls);
  callsRef.current = calls;

  const active = calls.some(needsPolling);

  useEffect(() => {
    if (!active) return;

    let cancelled = false;

    const tick = async () => {
      const live = callsRef.current.filter(needsPolling);
      await Promise.all(
        live.filter((c) => c.hunar_call_id).map((c) => api.refreshCall(c.id).catch(() => null)),
      );
      if (!cancelled) await reload().catch(() => null);
    };

    const timer = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [active, reload]);
}
