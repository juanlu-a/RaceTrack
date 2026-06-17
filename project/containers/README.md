# Containers

Long-running Fargate services that consume the simulation pipeline and expose metrics.

```
OpenF1 → ingest → save_session → start_simulation
                                      │  (1 SQS message per 10s bucket)
                                      ▼
        SQS racetrack-<env>-simulation-events
                                      │
                                      ▼
                  f1-consumer  ──────────────►  DynamoDB racetrack-<env>-simulation-metrics
                  (metrics per bucket)                    │
                                                          ▼
                                              metrics-exporter ──► GET /metrics (Prometheus)
```

## f1_consumer

Long-polls SQS, computes per-driver metrics for each 10s bucket
(`metrics.py`, pure/tested), and writes one DynamoDB item per bucket plus an
idempotent `META` item. Deletes messages only on success; the queue's
`maxReceiveCount=3` redrive routes poison messages to the DLQ.

Env: `SQS_QUEUE_URL`, `DYNAMODB_TABLE`, `AWS_DEFAULT_REGION`, `TTL_DAYS`,
optional `SQS_ENDPOINT`/`DYNAMODB_ENDPOINT` (LocalStack).

## metrics_exporter

Owns the simulation clock (`clock.py`, pure/tested):
`speed_factor = max_race_time_seconds / simulation_duration_seconds`,
`sim_race_time = elapsed_wallclock * speed_factor`. Each refresh it Queries the
selected simulation's buckets and publishes the currently-applicable bucket as
Prometheus gauges (with immediate catch-up for late buckets).

Env: `DYNAMODB_TABLE`, `AWS_DEFAULT_REGION`, `METRICS_PORT` (default 9100),
`REFRESH_SECONDS`, optional `SIMULATION_ID`, `DYNAMODB_ENDPOINT` (LocalStack).

## Tests

Pure logic is unit-tested in `project/tests/` (run by the standard
`pytest -m "not e2e"`):
- `f1_consumer_metrics.test.py`
- `metrics_exporter_clock.test.py`

## Local run against LocalStack

`project/docker-compose.yml` already enables `dynamodb`. With the stack up
(`make start`) and the SQS queue + DynamoDB table created against `:4566`:

```bash
# consumer
docker build -t f1-consumer project/containers/f1_consumer
docker run --rm --network racetrack \
  -e SQS_QUEUE_URL=... -e DYNAMODB_TABLE=racetrack-staging-simulation-metrics \
  -e SQS_ENDPOINT=http://localstack:4566 -e DYNAMODB_ENDPOINT=http://localstack:4566 \
  f1-consumer

# exporter
docker build -t metrics-exporter project/containers/metrics_exporter
docker run --rm --network racetrack -p 9100:9100 \
  -e DYNAMODB_TABLE=racetrack-staging-simulation-metrics \
  -e DYNAMODB_ENDPOINT=http://localstack:4566 \
  metrics-exporter
curl localhost:9100/metrics
```

## Deploy

CI (`deploy-staging.yml` / `deploy-prod.yml`, job `deploy-containers-*`) builds
and pushes both images to ECR (tagged with the git SHA + `latest`), then
`--force-new-deployment` rolls the ECS services. Services are created by
Terraform only when `enable_ecs = true` (see the env `.tfvars`); flip it on
after the first image push.
