# AI Hiring Assistant

A web app that screens candidates over the phone with a Hunar.AI voice agent and
puts their answers on a dashboard as structured data — not as a transcript
someone has to read.

**Stack:** React + Vite + TypeScript · FastAPI + async SQLAlchemy · Postgres in
production, SQLite locally.

---

## What it does

1. You define a role and the questions the agent should ask. Each question has a
   type — text, number, yes/no, or a fixed set of choices.
2. Those questions are compiled into a Hunar voice agent: the questions become
   an `agent_prompt` that tells it how to hold the conversation, and a
   `result_schema` that tells it exactly what JSON to hand back. The agent is
   provisioned lazily, on the first call the role places.
3. You add candidates (one at a time or by CSV) and start a screening call.
4. Hunar calls the candidate, runs the conversation, and posts webhooks back as
   the call progresses. The structured answers land as columns on the results
   dashboard, next to the recording.

The extraction is done by Hunar's own `result_schema`, so there is no second LLM
in this path — one fewer moving part, one fewer thing to pay for, and the
answers are typed at the source.

---

## Architecture

```
frontend/          React + Vite + TS
  src/api.ts       typed API client
  src/pages/       screening, results, and routes for the other two modules
backend/           FastAPI
  app/models.py    Job, Candidate, Call, WebhookEvent
  app/integrations/hunar.py    Hunar REST client + HMAC webhook verification
  app/services/screening.py    questions -> agent -> call -> results
  app/routers/     jobs, candidates, calls, webhooks
docs/              design notes
```

### One call pipeline, three modules

`Call` is not a "screening call" table. It is a record of *any* Hunar
conversation with *any* contact, discriminated by a `CallPurpose`:

| Purpose | Module |
|---|---|
| `SCREENING` | Screening candidates against a role (built) |
| `OUTREACH` | Calling people found by a people-search API (planned) |
| `ATTENDANCE_CHECKIN` | Daily attendance roll-call (planned) |

The webhook receiver, the status polling, the result storage and the dashboard
queries are all shared. Adding a module means adding a service and a router — it
never means touching the call plumbing. `Candidate.job_id` is nullable so
sourced people can be stored before they are attached to a role, and
`Candidate.source_metadata` is a JSON blob so a provider's profile renders
without a migration.

### Correlating a webhook with a call

We generate a `request_id`, send it with the call, and Hunar echoes it on every
webhook. Inbound events are matched on that first and the vendor's `call_id`
second — so a result that arrives before we have even stored the vendor's id
still finds its row.

Every webhook is written to `webhook_events` before it is processed, including
ones that fail verification. If a demo goes wrong, the evidence is in the table.

---

## Running it locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node 20+.

### Backend

```bash
cd backend
cp .env.example .env          # then edit it — see below
uv sync --group dev
uv run uvicorn app.main:app --reload
```

The API is on http://localhost:8000, with docs at `/docs`.

At minimum set `HUNAR_API_KEY` in `.env`. To explore without a key, set
`DRY_RUN_CALLS=true`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

http://localhost:5173. In dev, Vite proxies `/api` to the backend, so there is
no CORS setup to get wrong.

### Receiving webhooks locally

Hunar cannot reach `localhost`, so call results will never arrive without a
tunnel:

```bash
ngrok http 8000
# then set PUBLIC_BASE_URL=https://<id>.ngrok-free.app in backend/.env and restart
```

Without a tunnel the app still works — the UI falls back to polling Hunar for
each in-flight call, and says so in a banner.

### Tests

```bash
cd backend && uv run pytest && uv run ruff check .
```

---

## Handling the API key

The assignment asks for this explicitly, so it is worth being precise:

- The key lives in `backend/.env` locally and in the host's environment
  variables in production. `.env` is gitignored; `.env.example` documents every
  variable with no real values.
- The key never reaches the browser. The frontend talks only to our backend;
  only the backend talks to Hunar. Nothing prefixed `VITE_` ever contains a
  secret, because Vite inlines those into the public bundle.
- The same key is Hunar's HMAC secret for webhooks. Inbound webhooks are
  verified as base64 HMAC-SHA256 over `"{timestamp}." + raw_body`, compared with
  `hmac.compare_digest`, and rejected if the timestamp is more than 300 seconds
  old. Unverified webhooks get a 401 and are logged, not processed.
- The raw request body is used for verification, never a re-serialized copy of
  the parsed JSON — re-serializing changes key order and whitespace and would
  break the signature.

## Who can be called

Screening calls go to the number on the candidate's record — these are people
who applied for the role, so that is the point of the product. Two controls sit
around it:

- `DRY_RUN_CALLS=true` simulates the entire flow. No call is placed, and the
  results it produces are marked `_simulated` and labelled "Practice run" in the
  UI so they can never be mistaken for real answers.
- `ALLOWED_TEST_NUMBERS` is an **opt-in** restriction. Empty (the normal
  setting) means any candidate can be called. Fill it in and only those numbers
  are reachable — useful while testing, so a mistyped number cannot ring a
  stranger.

A candidate with no phone number is never called; that is the one hard rule.

Numbers are normalized on the way in, so a recruiter can type `9876543210`,
`098765 43210` or `+91 98765-43210` and all three are stored as `+919876543210`.
`DEFAULT_COUNTRY_CODE` decides what a number without one means.

The planned sourcing module is a different matter. Phone numbers returned by a
people-search API belong to people who never agreed to be called, so that module
will ship with simulation on by default and outreach chosen person by person.

---

## Deployment

- **Frontend → Vercel.** Root directory `frontend`, build `npm run build`,
  output `dist`. Set `VITE_API_BASE_URL` to the backend's URL.
- **Backend → Render or Railway.** Root directory `backend`, build
  `uv sync`, start
  `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Database → Neon.** Set `DATABASE_URL` to the Neon connection string with the
  `postgresql+asyncpg://` scheme.
- Then set `PUBLIC_BASE_URL` to the deployed backend URL so Hunar's webhooks
  arrive, and `CORS_ORIGINS` to the deployed frontend URL.

---

## Deliberate tradeoffs

These are choices, not oversights:

- **No Alembic.** Tables are created with `create_all`. The schema is a few days
  old and this is a time-boxed build; migrations are the first thing to add for
  a real deployment.
- **No auth.** There is no login, so anyone with the URL can use the deployed
  demo. Real use needs authentication before it holds candidate data.
- **Polling as a fallback.** Webhooks are the primary path; the UI polls only
  while a call is in flight, and only hits Hunar directly when the backend is
  not publicly reachable.
- **Simulated results are synthetic, not recorded.** Dry-run mode fabricates a
  plausible answer per question rather than replaying a captured call. It is
  there to exercise the flow, and it says so on screen.
