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
- AWS CLI configured with the `um_aws` profile

> **AWS profile note (important for Juanlu):** The default profile is the SSO work account, which expires. Always pass `--profile um_aws` to every `sam` command.

---

## Step 0 — Start Local Infrastructure

```bash
cd project/
docker compose up -d
```

This starts:
- **LocalStack** on `http://localhost:4566` — S3 and EventBridge
- **PostgreSQL 15** on `localhost:5432` — database `racetrack`, user/password `racetrack`

Verify both containers are healthy:
```bash
docker compose ps
```

---

## Step 0b — Build all lambdas (run once, or after code changes)

All commands below run from the `project/` directory using the unified template.

```bash
cd project/
sam build --profile um_aws
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

### Step 1b — Save to RDS

In production EventBridge triggers this automatically. For local testing, invoke it directly after Step 1:

```bash
sam local invoke SaveSessionFunction \
  --event lambdas/save_session/events/event.json \
  --env-vars env.json \
  --profile um_aws
```

> `lambdas/save_session/events/event.json` simulates the EventBridge payload. If you changed the session key, update the `key` field to `sessions/YOUR_KEY/raw.json`.

**Expected response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Session saved to RDS successfully",
    "session_key": "9158",
    "drivers_saved": 20,
    "laps_saved": 1240
  }
}
```

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
# Start infra
cd project/ && docker compose up -d

# Build all (once)
sam build --profile um_aws

# Step 1 — Ingest
sam local invoke IngestSessionFunction --event lambdas/ingest_session/events/event.json --env-vars env.json --profile um_aws

# Step 1b — Persist to RDS
sam local invoke SaveSessionFunction --event lambdas/save_session/events/event.json --env-vars env.json --profile um_aws

# Step 2 — List sessions
sam local invoke ListSessionFunction --event lambdas/list_session/events/event.json --env-vars env.json --profile um_aws

# Step 3 — List drivers
sam local invoke ListDriversFunction --event lambdas/list_drivers/events/event.json --env-vars env.json --profile um_aws

# Step 4 — Driver summary
sam local invoke DriverSummaryFunction --event lambdas/driver_summary/events/event.json --env-vars env.json --profile um_aws

# Step 5 — Driver laps
sam local invoke DriverLapsFunction --event lambdas/driver_laps/events/event.json --env-vars env.json --profile um_aws
```
