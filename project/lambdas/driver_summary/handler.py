"""
Lambda for API Gateway (HTTP API):
  GET /driver-summary?session_key=...  → Lista de pilotos de la sesión (OpenF1 drivers)
"""
import json

import requests


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _normalize_drivers(raw: list) -> list:
    return [
        {
            "pilotName": driver.get("full_name"),
            "pilotNumber": driver.get("driver_number"),
            "pilotTeam": driver.get("team_name"),
            "pilotCountry": driver.get("country_code"),
        }
        for driver in raw
    ]


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

    pilots = _normalize_drivers(data)
    return _json_response(200, {
        "sessionKey": session_key,
        "pilotCount": len(pilots),
        "pilots": pilots,
    })
