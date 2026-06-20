#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# monitoring_ips.sh
# Prints the public IPs / URLs of the Prometheus + Grafana ECS tasks.
#
# Fargate tasks get a fresh public IP on every (re)deploy or restart, so there
# is no stable URL — run this whenever you need the current links.
#
# Usage:
#   ./scripts/monitoring_ips.sh                 # env=staging, profile=racetrack
#   ENV=prod PROFILE=racetrack ./scripts/monitoring_ips.sh
#   AWS_PROFILE=racetrack ./scripts/monitoring_ips.sh
#
# Requires: awscli v2, jq, and credentials for the RaceTrack AWS account.
# ---------------------------------------------------------------------------
set -euo pipefail

ENV="${ENV:-staging}"
REGION="${REGION:-us-east-1}"
PROFILE="${PROFILE:-${AWS_PROFILE:-racetrack}}"
CLUSTER="racetrack-${ENV}-cluster"

aws_() { aws --profile "$PROFILE" --region "$REGION" "$@"; }

# public_ip <service-name> -> prints the task's public IPv4 (or "none")
public_ip() {
  local svc="$1" task eni ip
  task=$(aws_ ecs list-tasks --cluster "$CLUSTER" --service-name "$svc" \
    --query 'taskArns[0]' --output text 2>/dev/null || echo "None")
  [ "$task" = "None" ] || [ -z "$task" ] && { echo "none (no running task)"; return; }

  eni=$(aws_ ecs describe-tasks --cluster "$CLUSTER" --tasks "$task" \
    --query "tasks[0].attachments[?type=='ElasticNetworkInterface'].details[]" --output json \
    | jq -r '.[] | select(.name=="networkInterfaceId") | .value')
  [ -z "$eni" ] && { echo "none (no ENI yet)"; return; }

  ip=$(aws_ ec2 describe-network-interfaces --network-interface-ids "$eni" \
    --query 'NetworkInterfaces[0].Association.PublicIp' --output text 2>/dev/null || echo "None")
  [ "$ip" = "None" ] || [ -z "$ip" ] && { echo "none (no public IP)"; return; }
  echo "$ip"
}

echo "RaceTrack monitoring — env=${ENV} cluster=${CLUSTER} profile=${PROFILE}"
echo

GRAFANA_IP="$(public_ip "racetrack-${ENV}-grafana")"
PROM_IP="$(public_ip "racetrack-${ENV}-prometheus")"

case "$GRAFANA_IP" in
  none*) echo "Grafana    : ${GRAFANA_IP}" ;;
  *)     echo "Grafana    : http://${GRAFANA_IP}:3000   (admin / admin)" ;;
esac
case "$PROM_IP" in
  none*) echo "Prometheus : ${PROM_IP}" ;;
  *)     echo "Prometheus : http://${PROM_IP}:9090" ;;
esac
