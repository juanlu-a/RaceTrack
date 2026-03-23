# RaceTrack — Equipo 8

Serverless F1 data platform built with AWS Lambda, API Gateway, and DynamoDB.

## Structure

```
lambdas/
├── list_drivers/       → GET /list, /drivers, /cache  (fetch + store drivers by session)
├── get_session/        → GET /session                 (session details by session_key)
├── list_session/       → GET /sessions                (all sessions for a year)
└── drivers_summary/    → GET /summary                 (driver count by team and country)
```

## Lambdas

| Lambda | Endpoint | Param | DynamoDB |
|---|---|---|---|
| `list_drivers` | `GET /list` | `session_key` | No |
| `list_drivers` | `GET /drivers` | `session_key` | Write |
| `list_drivers` | `GET /cache` | `session_key` | Read |
| `get_session` | `GET /session` | `session_key` | No |
| `list_session` | `GET /sessions` | `year` | No |
| `drivers_summary` | `GET /summary` | `session_key` | No |

## Quick start

Each lambda is self-contained. Go into the lambda folder and run:

```bash
make build
make start-api   # starts local API on http://localhost:3000
```

For `list_drivers` (uses DynamoDB locally), run `make setup` first.
