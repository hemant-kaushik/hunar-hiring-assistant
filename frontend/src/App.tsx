import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";

import { api } from "./api";
import AttendancePage from "./pages/AttendancePage";
import JobDetailPage from "./pages/JobDetailPage";
import JobsPage from "./pages/JobsPage";
import ResultsPage from "./pages/ResultsPage";
import SourcingPage from "./pages/SourcingPage";
import type { Health } from "./types";

/**
 * Shell for all three assignment modules. Screening (Task 1) is live;
 * sourcing (Task 2) and attendance (Task 3) have their own routes so the
 * shape of the whole product is visible from the first screen.
 */
export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setUnreachable(true));
  }, []);

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/jobs" className="brand">
            AI Hiring Assistant
          </Link>
          <nav className="nav">
            <NavLink to="/jobs">Screening</NavLink>
            <NavLink to="/results">Results</NavLink>
            <NavLink to="/sourcing">Sourcing</NavLink>
            <NavLink to="/attendance">Attendance</NavLink>
          </nav>
        </div>
      </header>

      <main className="page">
        <ModeBanner health={health} unreachable={unreachable} />
        <Routes>
          <Route path="/" element={<Navigate to="/jobs" replace />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/sourcing" element={<SourcingPage />} />
          <Route path="/attendance" element={<AttendancePage />} />
          <Route path="*" element={<div className="empty">Page not found.</div>} />
        </Routes>
      </main>
    </>
  );
}

/**
 * Says what will happen when someone presses "Start screening call".
 *
 * Practice mode has to be unmistakable -- sample answers that look real are
 * worse than no answers. Everything else here is only shown when it would
 * otherwise cause silent confusion, and is phrased for the person using the
 * app, not the person who deployed it.
 */
function ModeBanner({ health, unreachable }: { health: Health | null; unreachable: boolean }) {
  if (unreachable) {
    return (
      <div className="banner err">
        Can't connect to the server right now. Check your connection, or try again in a
        moment.
      </div>
    );
  }
  if (!health) return null;

  if (health.dry_run_calls) {
    return (
      <div className="banner info">
        <strong>Practice mode.</strong> Nobody is called. Each call is filled in with
        example answers so you can try the whole process safely.
      </div>
    );
  }
  if (!health.hunar_configured) {
    return (
      <div className="banner warn">
        <strong>Calling isn't set up yet.</strong> You can add roles and candidates, but
        calls can't be placed until an administrator finishes the setup.
      </div>
    );
  }
  // Everything is configured and calls will connect: no banner. A warning shown
  // during normal operation is a warning people learn to ignore.
  return null;
}
