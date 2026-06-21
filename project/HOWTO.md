# RaceTrack — F1 Pipeline: Local Development Guide

This guide explains how to run the complete F1 data pipeline locally using SAM CLI and Docker.

---

## Architecture Overview

```
┌─────────────┐     ┌──────────────────┐     ┌────┐     ┌──────────────┐     ┌──────────────┐
│  API Gateway│────▶│  ingest_session  │────▶│ S3 │────▶│ EventBridge  │────▶│ save_session │
└─────────────┘     └──────────────────┘     └────┘     └──────────────┘     └──────┬───────┘
       │                                                                              │ RDS
       │                                                                              ▼
       │             ┌──────────────────┐                               ┌─────────────────────┐
       ├────────────▶│  list_session    │◀──────────────────────────────│      PostgreSQL      │
       ├────────────▶│  list_drivers    │◀──────────────────────────────│   sessions  table   │
       ├────────────▶│  driver_summary  │◀──────────────────────────────│   drivers   table   │
       └────────────▶│  driver_laps     │◀──────────────────────────────│   laps      table   │
                     └──────────────────┘                               └─────────────────────┘
```

**All lambdas share one API Gateway**, defined in `project/template.yaml`.

**Key principle:** Run `ingest_session` **once** per F1 session. It pulls everything from [OpenF1](https://openf1.org/) (session metadata, all drivers, all lap data) and persists it to S3 + PostgreSQL. Every other lambda reads exclusively from the database — no further OpenF1 calls.

---

## Project Structure

```
project/
├── template.yaml          ← Unified SAM template (one API GW, all lambdas)
├── env.json               ← Local env vars for all functions (LocalStack + Postgres)
├── docker-compose.yml     ← Local infra: LocalStack (S3+EventBridge) + PostgreSQL
├── HOWTO.md               ← This file
└── lambdas/
    ├── ingest_session/    ← Step 1a: fetch from OpenF1, save to S3
    ├── save_session/      ← Step 1b: EventBridge → write to RDS
    ├── list_session/      ← Step 2: GET /sessions
    ├── list_drivers/      ← Step 3: GET /drivers
    ├── driver_summary/    ← Step 4: GET /driver-summary
    └── driver_laps/       ← Step 5: GET /driver-laps
```

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- AWS CLI (`brew install awscli`)
- `make`
- AWS CLI configured with the `um_aws` profile

> **AWS profile note (Juanlu only):** The default profile on Juanlu's machine is an SSO work account that expires. Pass `PROFILE=um_aws` to every `make` command. Teammates with a correct default profile don't need this.

---

## Local Flow — How It Works

```
sam local invoke IngestSessionFunction
        │
        ├─ calls OpenF1 API
        ├─ saves raw JSON to LocalStack S3
        └─ fires event to LocalStack EventBridge
                │
                └─ EventBridge rule → triggers SaveSessionFunction (running inside LocalStack)
                        │
                        ├─ reads JSON from LocalStack S3
                        └─ writes sessions/drivers/laps to Postgres
```

`save_session` runs **inside LocalStack** (not via `sam local invoke`) so EventBridge can trigger it automatically — exactly like production.

---

## Step 0 — Bootstrap (first time only)

Run everything at once from `project/`:

```bash
cd project/

make all              # teammates (default AWS profile)
make all PROFILE=um_aws  # Juanlu only
```

This does in order:
1. `sam build` — compiles all lambdas and installs dependencies
2. `docker compose up -d` — starts LocalStack (S3 + EventBridge + Lambda) and Postgres
3. `./scripts/setup_localstack.sh` — deploys `SaveSessionFunction` into LocalStack and creates the EventBridge rule → Lambda target

Verify all containers are healthy:
```bash
docker compose ps
```

### After code changes to save_session

Re-run build + setup to redeploy the Lambda in LocalStack:

```bash
make build setup
```

---

## Step 1 — Ingest a Session

> Run this **once per session key**. It fetches everything from OpenF1 and saves to S3 + RDS.

```bash
sam local invoke IngestSessionFunction \
  --event lambdas/ingest_session/events/event.json \
  --env-vars env.json \
  --profile um_aws
```

**What it does:**
1. Calls OpenF1 for session info, all drivers, and all laps
2. Saves the bundled JSON to S3: `s3://racetrack-sessions/sessions/9158/raw.json`
3. Fires an EventBridge event `SessionIngested`

**Expected response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Session ingested successfully",
    "session_key": "9158",
    "s3_bucket": "racetrack-sessions",
    "s3_key": "sessions/9158/raw.json",
    "drivers_fetched": 20,
    "laps_fetched": 1240
  }
}
```

To use a different session, edit `lambdas/ingest_session/events/event.json` and change `session_key`.

---

### Step 1b — Save to RDS (automatic via EventBridge)

After Step 1, LocalStack EventBridge automatically triggers `SaveSessionFunction` (which runs inside LocalStack). You don't need to invoke it manually.

To check it ran, look at the LocalStack logs:
```bash
docker compose logs localstack --tail=30
```

You should see Lambda invocation logs there.

> **Manual fallback:** If you need to trigger it manually (e.g. for debugging):
> ```bash
> make invoke-save
> ```

Tables (`sessions`, `drivers`, `laps`) are created automatically on first run.

---

## Step 2 — List Available Sessions

```bash
sam local invoke ListSessionFunction \
  --event lambdas/list_session/events/event.json \
  --env-vars env.json \
  --profile um_aws
```

Filter by year: edit `lambdas/list_session/events/event.json` → `"queryStringParameters": { "year": "2024" }`.

**Expected response:**
```json
{
  "statusCode": 200,
  "body": {
    "count": 1,
    "year": null,
    "sessions": [
      {
        "session_key": "9158",
        "session_name": "Race",
        "circuit_short_name": "Bahrain",
        "country_name": "Bahrain",
        "year": 2024
      }
    ]
  }
}
```

---

## Step 3 — List Drivers in a Session

```bash
sam local invoke ListDriversFunction \
  --event lambdas/list_drivers/events/event.json \
  --env-vars env.json \
  --profile um_aws
```

**Expected response:**
```json
{
  "statusCode": 200,
  "body": {
    "sessionKey": "9158",
    "pilotCount": 20,
    "pilots": [
      {
        "pilotName": "Max Verstappen",
        "pilotNumber": 1,
        "pilotTeam": "Red Bull Racing",
        "pilotCountry": "NED"
      }
    ]
  }
}
```

---

## Step 4 — Driver Summary (Lap Stats)

```bash
sam local invoke DriverSummaryFunction \
  --event lambdas/driver_summary/events/event.json \
  --env-vars env.json \
  --profile um_aws
```

Default event: `session_key=9158`, `driver_number=1`. Edit the event file to change driver.

**Expected response:**
```json
{
  "statusCode": 200,
  "body": {
    "sessionKey": "9158",
    "driverNumber": 1,
    "driverName": "Max Verstappen",
    "team": "Red Bull Racing",
    "country": "NED",
    "stats": {
      "totalLaps": 57,
      "bestLapDuration": 91.743,
      "avgLapDuration": 96.812,
      "topSpeed": 328,
      "avgSpeed": 302.1
    }
  }
}
```

---

## Step 5 — Driver Laps

```bash
sam local invoke DriverLapsFunction \
  --event lambdas/driver_laps/events/event.json \
  --env-vars env.json \
  --profile um_aws
```

**Expected response:**
```json
{
  "statusCode": 200,
  "body": {
    "sessionKey": "9158",
    "driverNumber": 1,
    "lapCount": 57,
    "laps": [
      {
        "lapNumber": 1,
        "lapDuration": null,
        "i1Speed": 195,
        "i2Speed": 280,
        "stSpeed": 315,
        "isPitOutLap": true
      },
      {
        "lapNumber": 2,
        "lapDuration": 96.542,
        "i1Speed": 210,
        "i2Speed": 295,
        "stSpeed": 328,
        "isPitOutLap": false
      }
    ]
  }
}
```

> Speed fields: `i1Speed`/`i2Speed` = intermediate speed traps, `stSpeed` = finish straight. All in km/h.

---

## Testing with Postman (or curl)

### Start the local API server

Make sure `docker compose` is already running, then from `project/`:

```bash
make start-api                   # teammates
make start-api PROFILE=um_aws   # Juanlu only
```

This starts an HTTP server on **`http://localhost:3000`** that routes every request to the matching Lambda function, just like API Gateway would in production.

> Keep this terminal open. Each request spins up a Lambda container — you'll see the logs inline.

---

### Endpoints

| Step | Method | URL | Required params |
|---|---|---|---|
| 1 | GET | `http://localhost:3000/ingest` | `session_key` |
| 2 | GET | `http://localhost:3000/sessions` | *(none)* / `year` |
| 3 | GET | `http://localhost:3000/drivers` | `session_key` |
| 4 | GET | `http://localhost:3000/driver-summary` | `session_key`, `driver_number` |
| 5 | GET | `http://localhost:3000/driver-laps` | `session_key`, `driver_number` |

---

### Postman setup

1. Create a new collection called **RaceTrack Local**
2. Set a collection variable `base_url = http://localhost:3000`
3. Add one request per endpoint:

**Step 1 — Ingest session**
```
GET {{base_url}}/ingest?session_key=9158
```

**Step 2 — List sessions**
```
GET {{base_url}}/sessions
GET {{base_url}}/sessions?year=2024
```

**Step 3 — List drivers**
```
GET {{base_url}}/drivers?session_key=9158
```

**Step 4 — Driver summary**
```
GET {{base_url}}/driver-summary?session_key=9158&driver_number=1
```

**Step 5 — Driver laps**
```
GET {{base_url}}/driver-laps?session_key=9158&driver_number=1
```

---

### curl equivalents

```bash
# Step 1 — ingest (run once)
curl "http://localhost:3000/ingest?session_key=9158"

# Step 2 — list sessions
curl "http://localhost:3000/sessions"
curl "http://localhost:3000/sessions?year=2024"

# Step 3 — list drivers
curl "http://localhost:3000/drivers?session_key=9158"

# Step 4 — driver summary
curl "http://localhost:3000/driver-summary?session_key=9158&driver_number=1"

# Step 5 — driver laps
curl "http://localhost:3000/driver-laps?session_key=9158&driver_number=1"
```

> **Remember:** Hit `/ingest` first (Step 1). After that, EventBridge triggers `save_session` in LocalStack automatically and all other endpoints will return data.

---

## Local simulation + Grafana (full pipeline)

Grafana at http://localhost:3001 shows **simulation telemetry**, not API/RDS data. To populate it locally you need the full chain:

```
ingest → save_session → start_simulation → SQS → f1-consumer → DynamoDB
    → metrics-exporter → Prometheus → Grafana
```

### Three terminals

**Terminal 1 — bootstrap (once, or after `make stop`):**

```bash
cd project/
make all
# teammates with credential issues: make all PROFILE=um_aws
```

**Terminal 2 — local API:**

```bash
cd project/
make start-api
```

**Terminal 3 — ingest + simulate:**

```bash
cd project/
make demo-simulation
# optional: SESSION_KEY=9158 SIM_DURATION=120 make demo-simulation
```

`demo-simulation` will:
1. `GET /ingest?session_key=9158` (async OpenF1 fetch via EventBridge)
2. Wait until `/drivers` returns data (~1–3 min)
3. `POST /start-simulation` (publishes buckets to LocalStack SQS)
4. `f1-consumer` writes metrics to DynamoDB → Grafana updates

### Open Grafana

| URL | Notes |
|---|---|
| http://localhost:3001 | admin / admin |
| http://localhost:9090/targets | `metrics-exporter` should be **UP** |
| http://localhost:9100/metrics | raw `f1_*` gauges |

In the **RaceTrack — F1 Telemetry** dashboard, pick a **Simulation** from the dropdown (not “None”), set **Last 15 minutes**, refresh **5s**.

### Troubleshooting simulation / Grafana

| Problem | Fix |
|---|---|
| Grafana “No data”, Simulation = None | Run `make demo-simulation` (ingest alone is not enough) |
| `f1-consumer` not running | `make setup-simulation` then `docker compose up -d f1-consumer` |
| `env file .local/simulation.env not found` | Run `make setup-simulation` before starting `f1-consumer` |
| Ingest timeout | `docker compose logs localstack --tail=50` — check IngestWorker + SaveSession |
| Still empty after simulate | `curl -s localhost:9100/metrics \| grep ^f1_ \| head` — should show lines after ~30s |
| Consumer errors | `docker compose logs f1-consumer --tail=30` |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ExpiredTokenException` or credential errors | Add `--profile um_aws` to your SAM command |
| `Connection refused` on port 5432 | Run `docker compose up -d` from `project/` first |
| `NoSuchBucket` on S3 | `ingest_session` creates the bucket automatically — re-run Step 1 |
| `404 No laps/drivers found` | Run Steps 1 and 1b first to populate the database |
| SAM container can't reach Docker services | `host.docker.internal` is already set in `env.json` — check Docker Desktop is running |

---

## Quick Reference

```bash
cd project/

# ── First-time bootstrap ──────────────────────────────────────────────────────
make all                    # teammates
make all PROFILE=um_aws     # Juanlu only

# ── Start local API (Postman / curl on http://localhost:3000) ─────────────────
make start-api              # teammates
make start-api PROFILE=um_aws  # Juanlu only

# ── After code changes to save_session ────────────────────────────────────────
make build setup            # teammates
make build setup PROFILE=um_aws  # Juanlu only

# ── One-off lambda invocations (no HTTP server needed) ────────────────────────
make invoke-ingest PROFILE=um_aws
make invoke-sessions PROFILE=um_aws
make invoke-drivers PROFILE=um_aws
make invoke-summary PROFILE=um_aws
make invoke-laps PROFILE=um_aws

# ── Local simulation + Grafana ───────────────────────────────────────────────
make demo-simulation        # ingest + wait + start-simulation (needs start-api)
make setup-simulation       # SQS queue + DynamoDB table only
make invoke-start-simulation PROFILE=um_aws

# ── Logs & infra ──────────────────────────────────────────────────────────────
docker compose logs f1-consumer --tail=30
docker compose logs localstack --tail=30   # check EventBridge → save_session
make stop                                  # tear down containers
```
