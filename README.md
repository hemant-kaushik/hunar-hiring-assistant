# AI Hiring Assistant

A web app that screens candidates over the phone with a Hunar.AI voice agent, and
sources new candidates from a job description and reaches out to them the same
way — putting the answers on a dashboard as structured data, not as a transcript
someone has to read.

**Stack:** React + Vite + TypeScript · FastAPI + async SQLAlchemy · Postgres in
production, SQLite locally.

> **Just want to try it?** [docs/REVIEWER_GUIDE.md](docs/REVIEWER_GUIDE.md) walks
> through both modules step by step, no technical background needed.

---

## The two modules

### 1. Screening — call people who applied

1. Define a role and the questions the assistant should ask. Each question has a
   type: text, number, yes/no, or pick-from-a-list.
2. Those questions compile into a Hunar voice agent — an `agent_prompt` telling
   it how to hold the conversation, and a `result_schema` telling it exactly
   what JSON to return. The agent is provisioned lazily, on the first call.
3. Add candidates one at a time or by CSV, and start a screening call.
4. Hunar calls, runs the conversation, and posts webhooks back. The answers land
   as typed columns on the dashboard, next to the recording.

Extraction is done by Hunar's own `result_schema`, so there is no second LLM in
this path — one fewer moving part, one fewer thing to pay for, and answers that
are typed at the source.

### 2. Sourcing — find people who did not apply, then reach out

1. Paste a job description. A rule-based parser extracts titles, skills,
   location and seniority, and shows them **for editing** before anything runs —
   a filter you cannot correct is worse than no automation.
2. Search returns matching people, with their profile kept verbatim.
3. Shortlist the ones worth approaching, against a role.
4. Reach out. Their answers appear on the same dashboard as screening calls.

The outreach agent is deliberately **not** the screening agent. A screening call
assumes the person applied and expects to be assessed; an outreach call reaches
someone mid-day who has never heard of the company. So it opens by saying the
call is unsolicited, asks permission before continuing, treats "not interested"
as a good outcome to record and end on, and never claims a referral it wasn't
told about.

---

## Architecture

```
frontend/                    React + Vite + TS
  src/api.ts                 typed API client
  src/hooks.ts               live-updating call polling
  src/pages/                 screening, sourcing, results, attendance
backend/
  app/models.py              Job, Candidate, Call, AgentBinding, WebhookEvent
  app/phone.py               "9876543210" -> "+919876543210"
  app/integrations/
    hunar.py                 Hunar REST client + HMAC webhook verification
    people_search/           provider interface, PDL adapter, sample dataset
  app/services/
    call_pipeline.py         the generic call machinery, shared by all modules
    agents.py                provisioning an agent per (role, purpose)
    screening.py             Task 1: what makes a screening call a screening call
    outreach.py              Task 2: the cold-call conversation
    jd_parser.py             job description -> search filters
  app/routers/               jobs, candidates, calls, sourcing, webhooks
```

### One call pipeline, three modules

`Call` is not a "screening call" table. It is a record of *any* Hunar
conversation with *any* contact, discriminated by a `CallPurpose`:

| Purpose | Module |
|---|---|
| `SCREENING` | Screening people who applied (built) |
| `OUTREACH` | Calling people found by a search (built) |
| `ATTENDANCE_CHECKIN` | Daily attendance roll-call (designed, not built) |

`call_pipeline.py` knows nothing about what a call is *for*. Placing it,
tracking status, applying webhooks, storing results and simulating a dry run are
identical either way. Screening and outreach each supply only an agent and a set
of questions — which is why the second module needed no changes to the call
plumbing at all.

Supporting that: `Candidate.job_id` is nullable so sourced people can exist
before they are attached to a role, and `source_metadata` is a JSON blob so a
provider's profile renders without a migration.

### Correlating a webhook with a call

We generate a `request_id`, send it with the call, and Hunar echoes it on every
webhook. Inbound events match on that first and the vendor's `call_id` second —
so a result arriving before we have stored the vendor's id still finds its row.

Every webhook is written to `webhook_events` before processing, **including ones
that fail verification**, so a failed demo can be debugged after the fact.

---

## Running it locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
# backend
cd backend
cp .env.example .env          # then edit — see below
uv sync --group dev
uv run uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
```

Frontend on http://localhost:5173, API on http://localhost:8000 (docs at
`/docs`). In dev, Vite proxies `/api` to the backend, so there is no CORS setup
to get wrong.

**Nothing needs configuring to try it.** With no Hunar key, set
`DRY_RUN_CALLS=true` and the whole flow runs on simulated calls. With no
people-search key, sourcing uses a bundled dataset of 20 profiles and says so on
screen.

### Receiving webhooks locally

Hunar cannot reach `localhost`, so results never arrive without a tunnel:

```bash
ngrok http 8000
# set PUBLIC_BASE_URL to the https URL it prints, then restart the backend
```

Without one the app still works — it falls back to polling Hunar for in-flight
calls.

### Tests

```bash
cd backend && uv run pytest && uv run ruff check .
```

52 tests. They concentrate on the things that are easy to get subtly wrong and
expensive to get wrong in a demo: webhook signature verification, phone
normalization, question→schema compilation, provider contact redaction, and the
calling-window rules below.

---

## Configuration

| Variable | What it does |
|---|---|
| `HUNAR_API_KEY` | Hunar API key. Also the HMAC secret for verifying webhooks. |
| `PUBLIC_BASE_URL` | Where Hunar posts webhooks. Must be publicly reachable. |
| `DATABASE_URL` | SQLite locally; `postgresql+asyncpg://…` in production. |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API. |
| `DRY_RUN_CALLS` | `true` simulates every call. No phone rings. |
| `ALLOWED_TEST_NUMBERS` | **Opt-in** restriction. Empty means any candidate can be called; set it and only those numbers are reachable. |
| `DEFAULT_COUNTRY_CODE` | Assumed when a number is typed without one. |
| `CALL_TIMEZONE`, `EARLIEST_CALL_TIME`, `LATEST_CALL_TIME`, `CALL_ALLOWED_DAYS` | The calling window sent with every call. |
| `WEBHOOK_SIGNATURE_REQUIRED` | Reject unverified webhooks. Never disable in production. |
| `PDL_API_KEY` | People Data Labs key. Without it, sourcing uses sample data. |
| `PEOPLE_SEARCH_PROVIDER` | `auto` (default), `pdl`, or `sample`. |
| `SAMPLE_CONTACT_PHONE` | Makes the sample profiles callable for a demo. See below. |

---

## Handling the API key

The assignment asks for this explicitly, so it is worth being precise:

- The key lives in `backend/.env` locally and in the host's environment
  variables in production. `.env` is gitignored; `.env.example` documents every
  variable with no real values.
- **The key never reaches the browser.** The frontend talks only to our backend;
  only the backend talks to Hunar. Nothing prefixed `VITE_` contains a secret,
  because Vite inlines those into the public bundle.
- Inbound webhooks are verified as base64 HMAC-SHA256 over
  `"{timestamp}." + raw_body`, compared with `hmac.compare_digest`, and rejected
  if the timestamp is more than 300 seconds old. Unverified webhooks get a 401
  and are logged, not processed.
- Verification uses the **raw request body**, never a re-serialized copy of the
  parsed JSON — re-serializing changes key order and whitespace and breaks the
  signature.

## Who can be called

Screening calls go to people who applied, so calling them is the point. Around
that sit several guards:

- **`DRY_RUN_CALLS=true`** simulates everything. Results are marked `_simulated`
  and labelled "Practice run" in the UI, so they can never be mistaken for real
  answers.
- **`ALLOWED_TEST_NUMBERS`** is an opt-in allowlist. Empty means any candidate
  can be called; fill it in and only those numbers are reachable — useful while
  testing, so a mistyped number cannot ring a stranger.
- **A contact with no phone number is never called.** That is the one hard rule,
  and for sourced people it is a routine state rather than an error.
- **The sample dataset contains no phone numbers at all.** Inventing plausible
  ones would put real strangers behind a "Reach out" button. Fifteen of the
  twenty profiles instead borrow `SAMPLE_CONTACT_PHONE` — point it at a phone
  you control and the flow is fully demonstrable; leave it empty and they report
  a withheld number, which is what a real provider does on a free plan. The
  other five have no number, so the "add a number first" path is always visible.
- **Outreach is one person at a time, chosen by a human.** There is no bulk
  "call everyone" action, deliberately.

## People-search providers

`PDLProvider` talks to People Data Labs; `SampleProvider` is a local dataset of
20 fictional professionals. Selection is automatic: PDL when a key is set, sample
data otherwise, and **sample data as a fallback** when PDL is missing, out of
credits, rate-limited or down. The response always says which source answered, so
sample profiles are never mistaken for live data.

Two things to know about PDL's free tier: it gives 100 credits a month and *each
returned person costs one*, and contact fields come back as `true`/`false` flags
rather than actual values. `PersonResult` models that explicitly — `has_phone`
true with `phone` null means "a number exists but this plan won't release it",
which is what lets the UI explain why someone can't be called instead of showing
a blank.

---

## Notes from integrating with the Hunar API

Things that cost time and are not in the OpenAPI spec, recorded in case they save
someone else a debugging session:

- **Every endpoint lives under `/external/v1`.** Calling the bare paths returns
  an HTML 404 from the gateway, which reads like an outage rather than a wrong
  URL. The spec declares no `servers` entry, so the prefix must be applied
  client-side.
- **`PUT /agents/{id}/` rejects an update carrying `voice_persona` or `language`
  unless `persona_name` comes with it.** The existing persona has to be read
  back and passed through.
- **`guardrails` requires all three of `allowed_days`, `earliest_call_time` and
  `last_call_time`.** Omitting one fails validation rather than defaulting.
- **Calls are only permitted between 08:00 and 21:00** in the call's timezone.
  Ask for anything wider and the call is rejected outright; ask for a call
  outside those hours and it is queued rather than dialled. The app clamps its
  configured window to that range, and the UI labels a queued call as
  "Outside calling hours" rather than leaving a status nobody can interpret.
- **Status and results arrive as separate webhooks**, with the result trailing
  the status by a few seconds. Treating a `COMPLETED` call as finished stops the
  UI refreshing one beat before the answers land.
- **The extractor writes placeholder text** like `"NOT AVAILABLE"` into fields it
  could not fill, rather than omitting them. And a `result_schema` with a strict
  `enum` silently discards any answer that doesn't match one — "30 to 45 days"
  against buckets of 15/30/60 vanishes. Both are handled: the schema steers
  toward options instead of constraining, numeric questions accept text so
  "four or five years" survives, and the UI renders placeholder values as
  "Not answered".

---

## Deployment

- **Frontend → Vercel.** Root directory `frontend`, build `npm run build`,
  output `dist`. Set `VITE_API_BASE_URL` to the backend's URL.
- **Backend → Render or Railway.** Root directory `backend`, build `uv sync`,
  start `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Database → Neon.** `DATABASE_URL` with the `postgresql+asyncpg://` scheme.
- Then set `PUBLIC_BASE_URL` to the deployed backend URL so webhooks arrive, and
  `CORS_ORIGINS` to the deployed frontend URL.

---

## Deliberate tradeoffs

These are choices, not oversights:

- **No Alembic.** Tables are created with `create_all`. That creates new tables
  but never alters existing ones, which is why per-purpose agents went into an
  `agent_bindings` table rather than a new column on `jobs` — a column would have
  silently not applied to an existing database. Migrations are the first thing to
  add for a real deployment.
- **No auth.** Anyone with the URL can use the deployed demo. Real use needs
  authentication before it holds candidate data.
- **Rule-based JD parsing, not an LLM.** No extra key, no cost, no latency, no
  new failure mode in the demo path — and every extracted filter is editable
  before it is used, so a missed term costs seconds. An LLM would read unusual
  descriptions better and is the obvious upgrade.
- **Polling as a fallback.** Webhooks are the primary path; the UI polls only
  while a call is in flight or its answers are still due, and stops entirely once
  everything has settled.
- **Simulated results are synthetic, not recorded.** Dry-run mode fabricates a
  plausible answer per question rather than replaying a captured call. It exists
  to exercise the flow, and it says so on screen.
