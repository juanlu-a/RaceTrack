# RaceTrack — F1 Pipeline: Local Development Guide

This guide explains how to run the complete F1 data pipeline locally using SAM CLI and Docker.

---

## Architecture Overview

```
┌─────────────┐     ┌──────────────────┐     ┌────┐     ┌──────────────┐     ┌─────┐
│  API Gateway│────▶│  ingest_session  │────▶│ S3 │────▶│ EventBridge  │────▶│save_│
└─────────────┘     └──────────────────┘     └────┘     └──────────────┘     │sess.│
       │                                                                       └──┬──┘
       │                                                                          │ RDS
       │                                                                          ▼
       │             ┌──────────────────┐                               ┌─────────────────┐
       ├────────────▶│  list_session    │◀──────────────────────────────│    PostgreSQL    │
       ├────────────▶│  list_drivers    │◀──────────────────────────────│  sessions table │
       ├────────────▶│  driver_summary  │◀──────────────────────────────│  drivers table  │
       └────────────▶│  driver_laps     │◀──────────────────────────────│  laps table     │
                     └──────────────────┘                               └─────────────────┘
```

**Key principle:** `ingest_session` is run **once** per F1 session. It pulls everything from the [OpenF1 API](https://openf1.org/) (session metadata, all drivers, all lap data) and saves it to S3 and then to PostgreSQL. Every other lambda only reads from the database.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for LocalStack + Postgres)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- AWS CLI configured with the `um_aws` profile

> **AWS profile note (important for Juanlu):** The default AWS profile on this machine is the SSO work account, which expires. Always use `--profile um_aws` in every `sam` command to avoid credential errors.

---

## Step 0 — Start Local Infrastructure

All local AWS services (S3, EventBridge) run inside LocalStack. PostgreSQL mimics RDS.

```bash
# From the project/ directory
cd project/
docker compose up -d
```

This starts:
- **LocalStack** on `http://localhost:4566` — provides S3 and EventBridge
- **PostgreSQL 15** on `localhost:5432` — database `racetrack`, user/password `racetrack`

Wait until both containers report healthy:

```bash
docker compose ps
```

---

## Step 1 — Ingest a Session

> **Run this once per session.** It fetches all data from OpenF1 and saves it to S3 and RDS.

```bash
cd project/lambdas/ingest_session
sam build
sam local invoke IngestSessionFunction \
  --event events/event.json \
  --env-vars env.json \
  --profile um_aws
```

**What it does:**
1. Calls `openf1.org/v1/sessions?session_key=9158`
2. Calls `openf1.org/v1/drivers?session_key=9158`
3. Calls `openf1.org/v1/laps?session_key=9158`
4. Saves the bundled JSON to S3: `s3://racetrack-sessions/sessions/9158/raw.json`
5. Fires an EventBridge event `SessionIngested`

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

To test with a different session, edit `events/event.json` and change `session_key`.

---

### Step 1b — Save to RDS (EventBridge → PostgreSQL)

In production this runs automatically when EventBridge fires. For local testing, invoke it directly:

```bash
cd project/lambdas/save_session
sam build
sam local invoke SaveSessionFunction \
  --event events/event.json \
  --env-vars env.json \
  --profile um_aws
```

> The `events/event.json` file simulates the EventBridge payload with `bucket`, `key` and `session_key`. Make sure the S3 file exists first (run Step 1).

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

The `sessions`, `drivers` and `laps` tables are created automatically on first run.

---

## Step 2 — List Available Sessions

Returns all sessions stored in RDS. Optionally filter by year.

```bash
cd project/lambdas/list_session
sam build
sam local invoke ListSessionFunction \
  --event events/event.json \
  --env-vars env.json \
  --profile um_aws
```

To filter by year, update `events/event.json`:
```json
{
  "queryStringParameters": { "year": "2024" }
}
```

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

Returns all drivers for a given session from RDS.

```bash
cd project/lambdas/list_drivers
sam build
sam local invoke F1DriversApiFunction \
  --event events/event.json \
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

Returns computed statistics for a single driver: total laps, best lap time, average lap time, top speed, average speed.

```bash
cd project/lambdas/driver_summary
sam build
sam local invoke DriverSummaryFunction \
  --event events/event.json \
  --env-vars env.json \
  --profile um_aws
```

The default event uses `session_key=9158` and `driver_number=1`. Edit `events/event.json` to change the driver.

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

Returns every lap for a driver in a session, including sector speeds and pit-out flag.

```bash
cd project/lambdas/driver_laps
sam build
sam local invoke DriverLapsFunction \
  --event events/event.json \
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

> Speed fields: `i1Speed` / `i2Speed` = intermediate speed traps, `stSpeed` = finish straight speed trap. All in km/h.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ExpiredTokenException` or credential errors | Add `--profile um_aws` to your SAM command |
| `Connection refused` on port 5432 | Run `docker compose up -d` from `project/` first |
| `NoSuchBucket` | `ingest_session` creates the bucket automatically; re-run Step 1 |
| `404 No laps/drivers found` | Run Steps 1 and 1b first to populate the database |
| SAM container can't reach Docker services | Use `host.docker.internal` in `env.json` (already configured) |

---

## Quick Reference — All Commands

```bash
# Start infra
cd project/ && docker compose up -d

# Step 1 — Ingest
cd lambdas/ingest_session && sam build && sam local invoke IngestSessionFunction --event events/event.json --env-vars env.json --profile um_aws

# Step 1b — Persist to RDS
cd ../save_session && sam build && sam local invoke SaveSessionFunction --event events/event.json --env-vars env.json --profile um_aws

# Step 2 — List sessions
cd ../list_session && sam build && sam local invoke ListSessionFunction --event events/event.json --env-vars env.json --profile um_aws

# Step 3 — List drivers
cd ../list_drivers && sam build && sam local invoke F1DriversApiFunction --event events/event.json --env-vars env.json --profile um_aws

# Step 4 — Driver summary
cd ../driver_summary && sam build && sam local invoke DriverSummaryFunction --event events/event.json --env-vars env.json --profile um_aws

# Step 5 — Driver laps
cd ../driver_laps && sam build && sam local invoke DriverLapsFunction --event events/event.json --env-vars env.json --profile um_aws
```
