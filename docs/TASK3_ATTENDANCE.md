# Attendance for 1,000 people across 100 locations, without smartphones

**The question:** no smartphones, no apps — but LLMs and everything else exist.
You are an HR who must know, every day, who turned up at each of 100 sites.

**The shape of the problem:** 1,000 people, 100 locations, ~10 people per site,
365 days a year. That's 365,000 attendance facts to establish per year, and the
budget per fact is close to zero.

---

## 1. What the constraint actually removes

Losing smartphones doesn't remove *computing* — it removes the **screen you can
put in a worker's hand**. What survives is the thing almost every worker already
has: a phone that makes and receives calls, and can send a text.

So the interface has to be a **phone call**. And the reason that's now viable
rather than a 2005-era IVR nightmare is precisely the other half of the premise:
an LLM can hold an ordinary conversation and turn it into structured data. The
worker doesn't learn a menu. They say "yes, I'm at the Bhiwandi site" and the
system understands.

**What I would not build:**

| Alternative | Why not |
|---|---|
| Biometric terminals at each site | ₹8–15k × 100 sites in hardware, plus mounting, power, connectivity and repairs. Breaks silently, and a broken one produces *absence* records for people who came to work. |
| A web page on a feature phone | The premise excludes apps, and WAP-era browsing on a keypad is worse than a call in every way. |
| Paper register, photographed and emailed | Needs a camera phone and a literate scribe per site, and it's trivially falsified after the fact. |
| HR calls each site personally | 100 calls a day, ~2.5 hours of a salaried person, every day, forever — and no record beyond their notes. |

---

## 2. The design: two cheap signals, cross-checked

The core idea is **not** to find one reliable signal. It's to take two unreliable
but nearly free signals, and treat their *agreement* as proof and their
*disagreement* as the only thing a human ever looks at.

### Signal A — the worker's missed call (₹0)

Each site gets its own phone number. On arrival, the worker calls it and hangs up
after one ring. The system never answers, so **the call is free for everyone.**

- *Who* comes from caller ID. *Where* comes from which number was dialled.
  *When* is the timestamp.
- Numbers are enrolled once, when the person joins.
- This is a well-understood pattern in India — "missed call" services are how
  banks do balance enquiries. Nobody needs training.

What it proves: **a phone** was at that site at that time. Not a person. Which is
why there is a second signal.

### Signal B — the supervisor roll call (~90 seconds per site)

At a fixed time after shift start, the system places **one outbound call to each
site supervisor** — 100 calls, not 1,000. A voice agent asks them to run through
their team.

> "Good morning. Ten people are on the Bhiwandi list today. Can you tell me who's
> in?"
>
> "Everyone except Ramesh — he's on leave — and Sunita hasn't come yet."

An LLM turns that sentence into ten structured records: eight present, one on
approved leave, one absent-pending. No menu, no "press 1", and the supervisor
speaks whichever of the site's languages they actually speak.

### Reconciliation

| A (missed call) | B (supervisor) | Outcome |
|---|---|---|
| Present | Present | **Marked present. No human involved.** |
| Absent | Absent | **Marked absent.** |
| Present | Absent | Exception → verification call |
| Absent | Present | Present, flagged — phone lost/out of credit is the usual cause |

On a normal day the great majority land in the first two rows and cost nothing
but the supervisor call.

### The exception path

Only mismatches get an outbound call to the worker. The agent asks a simple
question and the LLM records the answer. At an assumed 5% mismatch rate that's
~50 calls a day — small enough to be affordable, large enough to keep everyone
honest.

### Fallbacks, in order

1. Missed call fails (no credit, no signal) → the supervisor roll call still
   covers them.
2. Supervisor unreachable → retry twice, then escalate to the area manager's
   roll call covering several sites.
3. No voice path at all → **SMS**, which works on the weakest signal a phone can
   hold. A one-word reply is enough, and an LLM reads it whether it says "yes",
   "haan", "present" or "ha".
4. Nothing worked → the day is marked **unverified**, not "absent". Silence must
   never cost someone a day's pay.

---

## 3. Identity: how much proof is worth buying

Attendance systems fail on identity, not on plumbing. The honest position is that
**you cannot fully prevent a colleague marking someone in** — you can only make
it more expensive than showing up.

- **Voice biometrics on the exception calls.** Enrol a short voiceprint when a
  person joins, verify it on any call that decides a disputed day. This is the
  place to spend the compute, because it's the only place the answer is contested.
- **Random spot checks.** Call ~5% of "present" workers directly each day. Cheap,
  and it changes behaviour far more than its volume suggests.
- **Anomaly detection over time.** A site reporting 100% attendance for sixty
  straight days is not a good site; it's an unaudited one. Flag the *pattern*, not
  the person.

I would deliberately **not** put voice verification on the daily path. It would
add cost and friction to the 95% of days nobody disputes.

---

## 4. What it costs

Assumptions stated so they can be argued with: Indian outbound voice at
₹0.50–1.00/min, 100 supervisor calls of ~90 seconds, a 5% exception rate, SMS at
₹0.15, and an LLM cost of roughly ₹0.05 per parsed conversation.

| Item | Volume/day | Cost/day |
|---|---|---|
| Worker missed calls | 1,000 | **₹0** (never connected) |
| Supervisor roll calls | 100 × 1.5 min | ₹75 – ₹150 |
| Exception calls | ~50 × 1 min | ₹25 – ₹50 |
| SMS fallback | ~50 | ₹8 |
| LLM parsing | ~150 conversations | ₹8 |
| **Total** | | **≈ ₹120 – ₹220 / day** |

That's roughly **₹3,600–6,600 a month for 1,000 people — about ₹4–7 per person
per month**, with no hardware, no installation and no site visits.

The comparison that matters isn't against a cheaper system, it's against the
status quo: one HR person spending 2.5 hours a day on roll-call phone calls costs
more than this in salary alone, and produces no queryable record at the end of it.

---

## 5. How it fails, and what happens when it does

| Failure | Consequence if ignored | Mitigation |
|---|---|---|
| Worker has no phone | Systematically marked absent — and it correlates with the poorest workers | Supervisor roll call is the primary record for them; never the missed call alone |
| Phone lent to a colleague | Buddy punching | Voice check on disputes, random spot calls, site-level anomaly detection |
| Supervisor marks everyone present | Whole site becomes fiction | Spot calls bypass the supervisor entirely; 100%-attendance streaks get flagged |
| Telecom outage in a region | Mass false absence | Mark **unverified**, never absent; reconcile late; alert HR that a region went dark |
| LLM mishears a name | Wrong person marked | Confidence threshold — ambiguity goes to the exception queue instead of being guessed |
| Two people, similar names, one site | Silent mis-assignment | Roll call reads back names; disambiguate at enrolment, not at runtime |
| Caller ID spoofed | Fraudulent presence | Rare and effortful; random callback defeats it |
| Shift crosses midnight | Day boundary errors | Attendance belongs to the *shift*, not the calendar date |

The pattern throughout: **every failure resolves toward "unverified", never
toward "absent".** A system that docks pay when the network is down will be
resisted, sabotaged, and rightly so.

---

## 6. What I would build first

1. **Weeks 1–2 — pilot, 5 sites, 50 people.** Missed-call check-in plus supervisor
   roll call. Reconcile by hand each evening and see where the mismatches truly
   come from — my 5% assumption is a guess, and it's the number the whole cost
   model rests on.
2. **Weeks 3–4.** Automate the exception calls. Add the SMS fallback. Add whichever
   two languages the pilot actually needed.
3. **Month 2.** Roll out to all 100 sites in waves of 20. Add anomaly detection
   once there's enough history for "normal" to mean something.
4. **Month 3.** Voice biometrics on disputes, if the pilot showed identity fraud
   is real here rather than theoretical. If it isn't, don't build it.

---

## 7. A note I would insist on

This is a system that tracks 1,000 people daily, and it should be built like one:
tell workers plainly what is recorded, keep voiceprints separately from
attendance records and delete them when someone leaves, retain recordings only as
long as a dispute window requires, and give people a way to contest a day that
doesn't route through the supervisor who marked them absent.

None of that is legal boilerplate. A workforce that believes the system is fair
cooperates with it, and a workforce that doesn't will defeat any design on this
page within a fortnight.

---

## 8. Why this sits in this repository

The call pipeline built for Tasks 1 and 2 already does most of this. `Call` is
not a "screening call" — it is any voice conversation with any contact,
discriminated by a `CallPurpose`, with `SCREENING`, `OUTREACH` and
`ATTENDANCE_CHECKIN` as its three values.

Placing calls, tracking status, verifying webhooks, extracting structured answers
via `result_schema` and storing results are all shared. Attendance needs a
service and a router — a roll-call agent, the reconciliation rules above, and the
missed-call receiver. **It needs no change to the call plumbing at all**, which is
the same claim Task 2 made and then demonstrated.
