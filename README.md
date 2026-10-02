# flyrank-background-jobs

Your first background job: move slow work out of the request path using
**Inngest**. A FastAPI API accepts report requests and returns `202` immediately;
an Inngest function does the ~8 seconds of "slow work" in visible steps, updating
a SQLite job store along the way. An hourly cron cleans up old finished jobs.

## 5-minute run

```bash
# 1. Install
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 2. Start the API (terminal 1)
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Start the Inngest dev server (terminal 2)
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest
# -> open http://127.0.0.1:8288 to watch functions execute live

# 4. Smoke test (terminal 3)
bash scripts/smoke.sh
```

## API

**POST /reports** — enqueue a report. Returns `202` immediately with the job id.
Send an `Idempotency-Key` header to make retries safe: reusing the same key
returns the *existing* job (same `job_id`, its current status) with **HTTP 200**
instead of creating a duplicate. (No header = always a new job.)

```bash
# 202, fast (<1s) — proves the slow work is async
curl -s -X POST http://127.0.0.1:8000/reports \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-123' \
  -d '{"title":"Q3 Metrics","sections":["growth","churn"]}'
# {"job_id":"<uuid>","status":"pending"}

# poll until complete
curl -s http://127.0.0.1:8000/reports/<uuid>
# {"job_id":"...","status":"running","progress":40,"result":null}
# ...
# {"job_id":"...","status":"complete","progress":100,
#  "result":{"title":"Q3 Metrics","sections_rendered":2,
#            "summary":"...","generated_at":"..."}}

# idempotency replay -> 200 with the SAME job_id
curl -s -X POST http://127.0.0.1:8000/reports \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-123' \
  -d '{"title":"anything else","sections":[]}'
# HTTP 200, same job_id, current status
```

**GET /reports/{job_id}** — `{"job_id", "status": "pending|running|complete|failed",
"progress": 0–100, "result": {...} | null}`. Unknown id → `404`.

## The Inngest function

`worker/functions.py` :: `generate-report`, triggered by `app/report.requested`,
configured with `retries=3`. It simulates ~8s of slow work in visible steps:

| step | what it does | job state after |
|---|---|---|
| `fetching-data` | `step.sleep(timedelta(seconds=3))` | running / 40% |
| `rendering-sections` | `step.sleep(timedelta(seconds=3))` | running / 80% |
| `finalizing` | `step.sleep(timedelta(seconds=2))` | complete / 100% + result payload |

(Note: in this SDK `step.sleep` takes **milliseconds** for an `int` argument, so we
pass `timedelta` to express seconds.)

Served at `/api/inngest` via `inngest.fast_api.serve(app, client, [functions])`.
The dev-server handshake: `curl http://127.0.0.1:8000/api/inngest` returns the
registration JSON (`functionIDs`, etc.).

## The cron

`cleanup-old-jobs` runs on `0 * * * *` (hourly) and deletes completed/failed jobs
older than 1 hour from the SQLite store, so the table doesn't grow forever.

## Job store

SQLite at `data/jobs.db` (created on startup, gitignored). All SQL is in
`app/store.py`:

```sql
jobs(id TEXT PK, idempotency_key TEXT UNIQUE, status TEXT, progress INT,
     result_json TEXT, created_at TEXT, updated_at TEXT)
```

## What was verified

- `POST /reports` returns `202` in ~110ms (proves async handoff).
- Polling shows `pending -> running -> complete` (~8s) with the result payload.
- Replaying the same `Idempotency-Key` returns `200` with the same `job_id`.
- `/api/inngest` serves the Inngest registration handshake (`function_count: 2`);
  the dev server synced the app and executed `generate-report` end-to-end.
- `cleanup_finished()` unit-checked: deletes only complete/failed jobs older
  than 1 hour.
- `generate-report` configured with `retries=3`; `cleanup-old-jobs` on cron
  `0 * * * *` (verified on the function objects).

## Environment notes (honest)

- In this sandbox, port 8000 was already taken by another project, so testing
  ran on **8001** (`uvicorn app.main:app --port 8001`, `BASE=http://127.0.0.1:8001
  bash scripts/smoke.sh`). Port 8000 is the default everywhere else.
- `npx inngest-cli@latest dev` hangs here: its `postinstall.js` uses
  `node-fetch`, which ignores the proxy env vars, so the dev-server binary
  download stalls. Workaround used: download the `inngest` binary directly
  (`https://cli.inngest.com/artifact/v1.45.1/inngest_1.45.1_linux_amd64.tar.gz`),
  then run `./bin/inngest dev -u http://127.0.0.1:8001/api/inngest --no-discovery`.
  The binary lives in `bin/` (gitignored).
- The sandbox's `no_proxy` contains bracketed IPv6 entries that break `httpx`;
  the shell needs `export no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1`
  before starting uvicorn/curl.
