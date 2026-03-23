# RaceTrack — Equipo 8

Serverless F1 data platform built with AWS Lambda, API Gateway, and DynamoDB.

## Structure

```
lambdas/
└── f1_drivers_api/      ← F1 drivers Lambda (list, import, cache)
    ├── handler.py
    ├── template.yaml
    ├── requirements.txt
    ├── docker-compose.yml
    ├── env.json
    ├── Makefile
    ├── README.md
    └── events/
        ├── event.json
        ├── event_cache.json
        └── event_list.json
```

## Lambdas

| Lambda | Endpoints | Description |
|---|---|---|
| `f1_drivers_api` | `/list` `/drivers` `/cache` | Fetch and store F1 driver data by session |

## Quick start

See `lambdas/f1_drivers_api/README.md` for setup instructions.
