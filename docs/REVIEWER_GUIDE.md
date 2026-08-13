# AI Hiring Assistant

A hiring assistant that **calls candidates on the phone**, holds a real
conversation with them, and puts their answers on a dashboard as tidy fields
instead of a recording someone has to sit through.

No login, no setup. Everything below happens in the browser. Each step says what
to do and **why it works that way** — the reasoning matters more than the clicks.

---

## Before you begin

**Calls only go out between 8:00 AM and 9:00 PM IST.**

> *Why:* the voice platform enforces this window, and rules on unsolicited calls
> exist for good reason. Outside those hours a call is **queued, not lost** — it
> shows as "Queued" rather than failing.

---

## Task 1 — Screening someone who applied

*About 5 minutes.*

**1.** Open the app. It lands on the **Screening** tab.

**2.** Click **Add a role** and give it a job title — or click **Use an example**
to fill the whole form in for you.

> *Why the example button:* so you can see the product work without first
> inventing a job description. Evaluating a tool shouldn't start with homework.

**3.** Under **What the assistant asks**, add your questions. Each has a type —
free text, a number, yes/no, or pick-from-a-list. Click **Save**.

> *Why types matter:* this is the heart of the design. Marking "years of
> experience" as a *number* is what lets the answer come back as data you can
> sort and filter, rather than a sentence someone has to read.
>
> *Why not just record the call and transcribe it:* a transcript still needs a
> human to read it. That's the work we're trying to remove, not relocate.

**4.** Under **Candidates**, add a name and phone number. **Use your own number.**

> *Why your own:* consent. The app shouldn't be used to ring someone who hasn't
> agreed to a test call, and that includes during a review.

**5.** Click **Start screening call**. Your phone rings within seconds.

> *Why one click per call:* there is no bulk-dial or automatic calling anywhere in
> this product. Every call is a deliberate action by a person.

**6.** Answer it and talk to the assistant as you would a recruiter. Hang up when
it says goodbye.

> *Why a conversation instead of a keypad menu:* people abandon "press 1 for…"
> menus, and a menu can't handle "about four years, maybe five."

**7.** Watch the row. Within about half a minute the **Answers** column fills in,
sorted into the questions you defined, with a link to the recording.

> *Why the short delay:* the platform sends the call outcome and the extracted
> answers as two separate messages a few seconds apart. The page updates itself —
> no need to refresh.

**8.** The **Results** tab shows every call across every role in one place.

> *Why:* a recruiter thinks in terms of "who have I spoken to this week," not
> role by role.

---

## Task 2 — Finding people who never applied, then reaching out

*About 5 minutes.*

> **Read this first.** This section runs on a **built-in sample dataset**, not a
> live people-search service — even though the integration for one (People Data
> Labs) is built, tested and ready.
>
> *Why:* a live search returns **real people who never asked to be contacted.**
> Ringing them to demonstrate a product isn't something I'm willing to do without
> their consent, and in most countries it isn't merely impolite — it's a legal
> problem.
>
> *If you would like to see it running on live data, just say so.* It's a
> configuration change — one API key — with **no code change at all.** I can have
> it switched on in a few minutes.

**1.** Click **Sourcing** in the top menu.

**2.** Paste any job description and click **Find candidates**.

> *Why a job description rather than a search form:* it's the document a recruiter
> already has. Retyping it into filter boxes is the chore being removed.

**3.** The app pulls out what to search for — titles, skills, location,
experience. **Every field is editable.** Fix anything it misread.

> *Why editable:* a filter you cannot correct is worse than no automation at all.
> The parser will misread unusual descriptions, and without an edit step you'd be
> stuck with a bad search and no way to see why.
>
> *Why it isn't an AI doing this parsing:* it would mean another paid service,
> more delay, and one more thing that can fail mid-demo. A simple rule-based
> reader you can *correct in two seconds* was the better trade. An AI parser is
> the obvious upgrade once it earns its keep.

**4.** Click **Find people**. Matching profiles appear.

> *Why the screen says "sample data":* the app labels where its results came
> from, rather than quietly passing demo profiles off as a live search. These are
> twenty fictional people, written to cover every case you'd meet in real
> results — including profiles whose phone number a real provider would withhold.

**5.** Tick the people worth approaching, choose a role, and click **Add them to
this role**.

> *Why a separate shortlist step:* "this person turned up in a search" and "I
> approve contacting this person" are different decisions, and collapsing them is
> how people get cold-called by mistake.

**6.** Click **Reach out** on anyone with a phone number. Their responses appear
under **What they said**.

> *Why this call sounds different from Task 1:* a screening call reaches someone
> who applied and expects to be assessed. An outreach call reaches a stranger
> mid-workday. So it opens by saying the call is unsolicited, asks permission
> before continuing, and treats "not interested" as a perfectly good answer to
> record and end on.

---

## Task 3 — Attendance for 1,000 people without smartphones

*About 3 minutes to read.*

Click **Attendance** in the top menu. This one is a **written answer**, not
software — the question asked what you'd do, not what you'd build.

The short version: take two signals that each cost almost nothing — a free missed
call from each worker, and one 90-second automated call to each site supervisor —
and treat their **agreement** as proof. Only the disagreements, around 5% of
people on a normal day, ever reach a human. It works out at roughly **₹4–7 per
person per month** with no hardware anywhere.

> *Why it's worth your three minutes:* the page carries the costing and the
> failure analysis, including the rule the whole design turns on — **every failure
> resolves to "unverified", never to "absent"**. A system that docks someone's pay
> because the mobile network went down will be defeated by its own workforce
> inside a fortnight.

The full write-up, with the rollout plan and the alternatives I rejected, is in
`docs/TASK3_ATTENDANCE.md` in the repository.

---

## What's worth noticing

- **The answers are structured, not transcribed.** "About four years, maybe five"
  lands in an experience field. Nobody re-reads the call.
- **The outreach call is a different conversation, by design** — not the same
  script pointed at a different list.
- **Nothing is dialled automatically.** Every call needs a click.

---

## About the phone calls

- Calls happen **only** when you click — never in the background, never in bulk.

  > *Why:* automatic dialling of people sourced from a data provider is a legal
  > problem in most countries, not just a rude one.

- The demo profiles in Sourcing deliberately carry **no phone numbers**.

  > *Why:* inventing plausible numbers would put a real stranger behind a "Reach
  > out" button. They show as "number withheld" — which is also what a real
  > provider returns on a free plan.

- **If your phone doesn't ring**, the voice platform's test key is limited to
  registered numbers.

  > *Why it's not a bug:* the restriction sits with the platform, not this app.
  > Let me know and I'll add your number, or walk you through it on a call.

---

## About the API key

The assignment asked for this specifically, so it's worth being precise:

- The key lives in the hosting provider's environment settings — **not in the
  source code, not in the repository, and not in the repository's history.**
- **The key never reaches your browser.** The page talks only to our own server;
  only that server talks to the voice platform.
- Results arriving back from the platform are cryptographically signed, and
  verified before anything is saved.

  > *Why that last one matters:* without it, anyone who guessed the address could
  > post fake interview answers into the dashboard.

---

## Known limits, chosen on purpose

- **No login.** Anyone with the link can use the demo.

  > *Why left out:* real use needs proper accounts before it holds candidate data,
  > and a token login bolted on for a demo would be worse than none — it would
  > imply the data is protected when it isn't.

- **The Attendance tab is a written design**, deliberately not working software.

  > *Why:* the third question asked what you would *do*, not what you would ship.
  > Building it would have demonstrated less than thinking it through — the cost
  > model and the failure analysis are the answer, and neither needs code.

---

Questions, or anything that doesn't behave — please just ask.
