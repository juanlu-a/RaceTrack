# Monitoring — Prometheus + Grafana

The observability tail of the pipeline:

```
f1-consumer -> DynamoDB -> metrics-exporter (/metrics :9100) -> Prometheus -> Grafana
```

`metrics-exporter` exposes per-driver Prometheus gauges (speed, position, gap to
leader, lap, track x/y) plus simulation race-time/progress. Prometheus scrapes
it; Grafana visualises it via the pre-provisioned **RaceTrack — F1 Telemetry**
dashboard.

## Local (docker-compose)

From `project/`:

```bash
make start          # or: docker compose up -d
```

| Service          | URL                          | Notes                                  |
| ---------------- | ---------------------------- | -------------------------------------- |
| Grafana          | http://localhost:3001        | anonymous viewer on; admin / admin     |
| Prometheus       | http://localhost:9090        | check Status → Targets                 |
| metrics-exporter | http://localhost:9100/metrics | raw gauges                             |

Grafana auto-loads the Prometheus datasource and the **RaceTrack — F1 Telemetry**
dashboard. Pick a simulation from the **Simulation** dropdown; optionally filter
charts with the **Drivers** variable.

### Dashboard panels

| Section | Panels |
| --- | --- |
| Race overview | Progress gauge, race time, leader speed, max speed, driver count |
| Live standings | Table with position, speed, gap and lap (with inline gauges) |
| Speed | Time series + horizontal bar gauge snapshot |
| Gaps & laps | Gap to leader, lap number progression |
| Position & track | Position over time (P1 at top), track map scatter |

> **Local with data:** from `project/` run `make all`, then `make start-api` (terminal 2)
> and `make demo-simulation` (terminal 3). See `HOWTO.md` § “Local simulation + Grafana”.

Grafana is mapped to host port **3001** so it doesn't collide with
`sam local start-api` (port 3000).

## Production (ECS Fargate — gated, default off)

Disabled by default. The images are built and pushed to ECR on every deploy, but
the services are only created when `enable_monitoring = true`.

To turn it on:

1. Set `enable_monitoring = true` in `terraform/environments/<env>.tfvars`
   (requires `enable_ecs = true`).
2. Deploy. Terraform creates the Prometheus + Grafana Fargate services and an
   ECS **Service Connect** namespace so Prometheus scrapes `metrics-exporter:9100`
   and Grafana queries `prometheus:9090` by stable name.
3. Reach the UIs at each task's **public IP** (no load balancer): Grafana on
   `grafana_port` (3000), Prometheus on `prometheus_port` (9090). Lock down
   access with `monitoring_ingress_cidrs`.

Cost when enabled: ~2 extra Fargate tasks + public IPs. There is no persistent
volume — dashboards/config are baked into the images, so Grafana state is
ephemeral across task restarts. Flip back to `false` when idle.

## Files

- `prometheus/prometheus.yml` — scrape config (shared by local + prod).
- `prometheus/Dockerfile` — bakes the config for the prod image.
- `grafana/provisioning/` — datasource + dashboard providers.
- `grafana/dashboards/racetrack.json` — the dashboard.
- `grafana/Dockerfile` — bakes provisioning + dashboards for the prod image.
