#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# monitoring_ips.sh
# Prints the public Grafana URL (via its ALB) for an environment.
#
# Grafana now runs in a private subnet (no public IP) behind a public ALB, so
# its URL is STABLE (the ALB DNS name). Prometheus and the metrics-exporter are
# internal only (not internet-reachable) — query Prometheus through Grafana.
#
# Usage:
#   ./scripts/monitoring_ips.sh                 # env=staging, profile=racetrack
#   ENV=prod ./scripts/monitoring_ips.sh
#   AWS_PROFILE=racetrack ./scripts/monitoring_ips.sh
#
# Requires: awscli v2 and credentials for the RaceTrack AWS account.
# ---------------------------------------------------------------------------
set -euo pipefail

ENV="${ENV:-staging}"
REGION="${REGION:-us-east-1}"
PROFILE="${PROFILE:-${AWS_PROFILE:-racetrack}}"
ALB_NAME="racetrack-${ENV}-grafana-alb"

aws_() { aws --profile "$PROFILE" --region "$REGION" "$@"; }

echo "RaceTrack monitoring — env=${ENV} profile=${PROFILE}"
echo

DNS=$(aws_ elbv2 describe-load-balancers --names "$ALB_NAME" \
  --query 'LoadBalancers[0].DNSName' --output text 2>/dev/null || echo "None")

if [ "$DNS" = "None" ] || [ -z "$DNS" ]; then
  echo "Grafana    : none (ALB not found — is enable_monitoring=true and deployed?)"
else
  echo "Grafana    : http://${DNS}   (login: admin)"
fi
echo "Prometheus : internal only (VPC) — query it through Grafana's datasource"
