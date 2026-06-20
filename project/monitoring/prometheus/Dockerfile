# Prometheus image with the RaceTrack scrape config baked in (used by the gated
# prod ECS stack; the local docker-compose bind-mounts the config instead).
FROM prom/prometheus:v2.54.1

COPY prometheus.yml /etc/prometheus/prometheus.yml
