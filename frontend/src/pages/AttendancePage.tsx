/**
 * Task 3 — the written answer, rendered in the app so it can be read without
 * cloning the repository. The full version lives in docs/TASK3_ATTENDANCE.md.
 */
export default function AttendancePage() {
  return (
    <>
      <h1>Attendance without smartphones</h1>
      <p className="subtitle">
        1,000 people, 100 locations, every day — using ordinary phone calls, with nothing
        for anyone to install. A design, not working software.
      </p>

      <div className="panel doc">
        <h2>What the constraint actually removes</h2>
        <p>
          Losing smartphones doesn't remove computing. It removes the{" "}
          <strong>screen you can put in a worker's hand</strong>. What survives is what
          nearly every worker already carries: a phone that makes calls and sends texts.
        </p>
        <p>
          So the interface has to be a phone call — and the other half of the premise is
          what makes that bearable rather than a 2005-era menu system. An LLM can hold an
          ordinary conversation and turn it into structured data. Nobody learns a menu.
        </p>

        <h2>Two cheap signals, cross-checked</h2>
        <p>
          The idea is not to find one reliable signal. It is to take two unreliable but
          nearly free ones, treat their <strong>agreement</strong> as proof, and let their{" "}
          <strong>disagreement</strong> be the only thing a human ever looks at.
        </p>

        <h3>Signal A — the worker's missed call (free)</h3>
        <p>
          Each site has its own number. On arrival the worker calls it and hangs up. The
          system never answers, so <strong>the call costs nobody anything</strong>. Caller
          ID gives the person, the dialled number gives the place, the timestamp gives the
          time. It proves a <em>phone</em> was there — not a person, which is why there is a
          second signal.
        </p>

        <h3>Signal B — the supervisor roll call (~90 seconds)</h3>
        <p>
          One outbound call per site — 100 calls, not 1,000. A voice agent asks the
          supervisor to run through the team. "Everyone except Ramesh, he's on leave, and
          Sunita hasn't come yet" becomes ten structured records. They speak whichever
          language they actually speak.
        </p>

        <h3>Reconciliation</h3>
        <table className="doc-table">
          <thead>
            <tr>
              <th>Missed call</th>
              <th>Supervisor</th>
              <th>Outcome</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Present</td>
              <td>Present</td>
              <td>Marked present — no human involved</td>
            </tr>
            <tr>
              <td>Absent</td>
              <td>Absent</td>
              <td>Marked absent</td>
            </tr>
            <tr>
              <td>Present</td>
              <td>Absent</td>
              <td>Exception → verification call</td>
            </tr>
            <tr>
              <td>Absent</td>
              <td>Present</td>
              <td>Present, flagged — usually a flat battery</td>
            </tr>
          </tbody>
        </table>
        <p>
          Only mismatches trigger an outbound call to the worker. At an assumed 5% mismatch
          rate that is ~50 calls a day.
        </p>

        <h2>What it costs</h2>
        <p className="muted">
          Assuming Indian outbound voice at ₹0.50–1.00/min, 100 roll calls of ~90 seconds, a
          5% exception rate, and ~₹0.05 per parsed conversation.
        </p>
        <table className="doc-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Volume/day</th>
              <th>Cost/day</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Worker missed calls</td>
              <td>1,000</td>
              <td>₹0 — never connected</td>
            </tr>
            <tr>
              <td>Supervisor roll calls</td>
              <td>100 × 1.5 min</td>
              <td>₹75 – ₹150</td>
            </tr>
            <tr>
              <td>Exception calls</td>
              <td>~50 × 1 min</td>
              <td>₹25 – ₹50</td>
            </tr>
            <tr>
              <td>SMS fallback + LLM parsing</td>
              <td>~200</td>
              <td>₹16</td>
            </tr>
            <tr>
              <td>
                <strong>Total</strong>
              </td>
              <td />
              <td>
                <strong>≈ ₹120 – ₹220 / day</strong>
              </td>
            </tr>
          </tbody>
        </table>
        <p>
          Roughly <strong>₹4–7 per person per month</strong>, with no hardware, no
          installation and no site visits. The comparison that matters is not a cheaper
          system — it is one HR person spending 2.5 hours a day on roll-call calls, which
          costs more in salary alone and leaves no queryable record.
        </p>

        <h2>How it fails</h2>
        <table className="doc-table">
          <thead>
            <tr>
              <th>Failure</th>
              <th>Mitigation</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Worker has no phone</td>
              <td>Supervisor roll call is their primary record, never the missed call alone</td>
            </tr>
            <tr>
              <td>Phone lent to a colleague</td>
              <td>Voice check on disputes, random spot calls, site-level anomaly detection</td>
            </tr>
            <tr>
              <td>Supervisor marks everyone present</td>
              <td>Spot calls bypass them; 100%-attendance streaks are flagged as unaudited</td>
            </tr>
            <tr>
              <td>Regional telecom outage</td>
              <td>Mark unverified, never absent; alert HR that a region went dark</td>
            </tr>
            <tr>
              <td>LLM mishears a name</td>
              <td>Ambiguity goes to the exception queue instead of being guessed</td>
            </tr>
            <tr>
              <td>Shift crosses midnight</td>
              <td>Attendance belongs to the shift, not the calendar date</td>
            </tr>
          </tbody>
        </table>
        <p>
          The pattern throughout:{" "}
          <strong>every failure resolves toward "unverified", never toward "absent"</strong>.
          A system that docks pay when the network is down will be resisted, and rightly so.
        </p>

        <h2>Identity — how much proof is worth buying</h2>
        <p>
          You cannot fully prevent a colleague marking someone in. You can only make it more
          expensive than showing up. Voice biometrics belong on the{" "}
          <strong>disputed</strong> calls, not the daily path — that is the only place the
          answer is contested, and putting them everywhere adds cost and friction to the 95%
          of days nobody argues about.
        </p>

        <h2>A note I would insist on</h2>
        <p>
          This tracks 1,000 people daily and should be built like it: tell workers what is
          recorded, keep voiceprints apart from attendance and delete them when someone
          leaves, and give people a way to contest a day that doesn't route through the
          supervisor who marked them absent. A workforce that believes the system is fair
          cooperates with it; one that doesn't will defeat any design here within a
          fortnight.
        </p>

        <h2>Why this sits in this repository</h2>
        <p>
          The call pipeline built for the first two modules already does most of this.{" "}
          <code>Call</code> is not a "screening call" — it is any voice conversation with any
          contact, discriminated by a <code>CallPurpose</code>, whose three values are{" "}
          <code>SCREENING</code>, <code>OUTREACH</code> and <code>ATTENDANCE_CHECKIN</code>.
          Attendance needs a roll-call agent, the reconciliation rules above, and a
          missed-call receiver. It needs <strong>no change to the call plumbing at all</strong>
          — the same claim the sourcing module made, and then demonstrated.
        </p>

        <p className="muted">
          The full write-up, including the rollout plan and the alternatives I rejected, is
          in <code>docs/TASK3_ATTENDANCE.md</code> in the repository.
        </p>
      </div>
    </>
  );
}
