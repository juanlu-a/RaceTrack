# Grafana image with the RaceTrack datasource + dashboards baked in (used by the
# gated prod ECS stack; the local docker-compose bind-mounts these instead).
FROM grafana/grafana:11.2.0

COPY provisioning /etc/grafana/provisioning
COPY dashboards /var/lib/grafana/dashboards
