"""
Lambda for API Gateway (HTTP API):
  GET /summary?session_key=...  → Returns a summary of drivers grouped by team and country
"""
import json
from collections import Counter
import requests


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    session_key = (params.get("session_key") or "").strip()
    if not session_key:
        return _json_response(400, {
            "error": "Missing query parameter: session_key",
            "example": "?session_key=9158",
        })

    url = f"https://api.openf1.org/v1/drivers?session_key={session_key}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        return _json_response(502, {"error": "Failed to call OpenF1 API", "details": str(e)})

    if not isinstance(data, list):
        return _json_response(502, {"error": "Unexpected response from OpenF1"})

    teams = Counter(d.get("team_name") for d in data)
    countries = Counter(d.get("country_code") for d in data)

    return _json_response(200, {
        "sessionKey": session_key,
        "totalDrivers": len(data),
        "byTeam": [{"team": t, "driverCount": c} for t, c in sorted(teams.items())],
        "byCountry": [{"country": c, "driverCount": n} for c, n in sorted(countries.items(), key=lambda x: -x[1])],
    })
