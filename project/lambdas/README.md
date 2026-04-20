# RaceTrack — Equipo 8

Serverless F1 data platform built with AWS Lambda, API Gateway, S3, EventBridge and PostgreSQL (RDS).

## Architecture

```
API GW → ingest_session ──→ S3 (raw JSON) ──→ EventBridge ──→ save_session ──→ RDS (PostgreSQL)
                                                                                      ↑
API GW → list_session   ─────────────────────────────────────────────────────────────┘
API GW → list_drivers   ─────────────────────────────────────────────────────────────┘
API GW → driver_summary ─────────────────────────────────────────────────────────────┘
API GW → driver_laps    ─────────────────────────────────────────────────────────────┘
```

**Key design principle:** Run `ingest_session` once per session. It fetches all data from OpenF1 (session info, drivers, laps) and persists everything to RDS. After that, all other lambdas read exclusively from RDS — no further OpenF1 calls.

## Structure

```
lambdas/
├── ingest_session/   → GET /ingest?session_key=         (bulk fetch OpenF1 → S3 → EventBridge)
├── save_session/     → EventBridge trigger               (S3 read → RDS write)
├── list_session/     → GET /sessions[?year=]             (query sessions table in RDS)
├── list_drivers/     → GET /drivers?session_key=         (query drivers table in RDS)
├── driver_summary/   → GET /driver-summary?session_key=&driver_number=  (lap stats from RDS)
└── driver_laps/      → GET /driver-laps?session_key=&driver_number=     (laps list from RDS)
```

## Endpoints

| Lambda | Endpoint | Required Params | Description |
|---|---|---|---|
| `ingest_session` | `GET /ingest` | `session_key` | Fetch all F1 data and save to S3+RDS |
| `save_session` | EventBridge | *(automatic)* | Read S3, write to RDS |
| `list_session` | `GET /sessions` | *(none)* | List all sessions |
| `list_session` | `GET /sessions` | `year` | Filter sessions by year |
| `list_drivers` | `GET /drivers` | `session_key` | List drivers in a session |
| `driver_summary` | `GET /driver-summary` | `session_key`, `driver_number` | Driver lap stats |
| `driver_laps` | `GET /driver-laps` | `session_key`, `driver_number` | All laps for a driver |

## RDS Schema

```sql
sessions  (session_key PK, session_name, session_type, circuit_short_name, country_name,
           location, date_start, date_end, year, meeting_key)

drivers   (session_key, driver_number PK, full_name, team_name, country_code)

laps      (session_key, driver_number, lap_number PK, lap_duration, i1_speed,
           i2_speed, st_speed, is_pit_out_lap)
```

> Tables are created automatically by `save_session` on first run (CREATE TABLE IF NOT EXISTS).

## Local Development

See [`../HOWTO.md`](../HOWTO.md) for the full step-by-step guide including Docker setup and SAM commands.
