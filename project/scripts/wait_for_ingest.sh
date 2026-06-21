#!/usr/bin/env bash
# Poll GET /drivers until the session is queryable (save_session finished).
set -euo pipefail

SESSION_KEY="${1:-9158}"
API_BASE="${API_BASE:-http://localhost:3000}"
MAX_TRIES="${MAX_TRIES:-60}"
SLEEP_SEC="${SLEEP_SEC:-10}"

echo "Waiting for session ${SESSION_KEY} at ${API_BASE}/drivers ..."
for i in $(seq 1 "$MAX_TRIES"); do
  code=$(curl -sS -o /tmp/racetrack_drivers.json -w "%{http_code}" \
    "${API_BASE}/drivers?session_key=${SESSION_KEY}" 2>/dev/null || echo "000")
  count=$(python3 -c "import json; d=json.load(open('/tmp/racetrack_drivers.json')); print(d.get('pilotCount') or len(d.get('pilots') or []))" 2>/dev/null || echo 0)
  echo "  try ${i}/${MAX_TRIES}: HTTP ${code} pilotCount=${count}"
  if [ "$code" = "200" ] && [ "${count:-0}" -ge 1 ]; then
    echo "Session ${SESSION_KEY} is ready."
    exit 0
  fi
  sleep "$SLEEP_SEC"
done

echo "Timed out waiting for ingest. Check: docker compose logs localstack --tail=40"
exit 1
