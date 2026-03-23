"""
Lambda for API Gateway (HTTP API):
  GET /sessions?year=...  → Returns all F1 sessions from OpenF1 for a given year
"""
import json
import requests


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    year = (params.get("year") or "").strip()
    if not year:
        return _json_response(400, {
            "error": "Missing query parameter: year",
            "example": "?year=2023",
        })

    url = f"https://api.openf1.org/v1/sessions?year={year}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        return _json_response(502, {"error": "Failed to call OpenF1 API", "details": str(e)})

    if not isinstance(data, list):
        return _json_response(502, {"error": "Unexpected response from OpenF1"})

    sessions = [
        {
            "sessionKey": s.get("session_key"),
            "sessionName": s.get("session_name"),
            "sessionType": s.get("session_type"),
            "dateStart": s.get("date_start"),
            "location": s.get("location"),
            "countryName": s.get("country_name"),
            "circuitShortName": s.get("circuit_short_name"),
        }
        for s in data
    ]
    return _json_response(200, {
        "year": year,
        "sessionCount": len(sessions),
        "sessions": sessions,
    })
