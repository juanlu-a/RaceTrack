"""
Lambda for API Gateway (HTTP API):
  GET /session?session_key=...  → Returns session details from OpenF1 for a given session key
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
    session_key = (params.get("session_key") or "").strip()
    if not session_key:
        return _json_response(400, {
            "error": "Missing query parameter: session_key",
            "example": "?session_key=9158",
        })

    url = f"https://api.openf1.org/v1/sessions?session_key={session_key}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        return _json_response(502, {"error": "Failed to call OpenF1 API", "details": str(e)})

    if not isinstance(data, list) or len(data) == 0:
        return _json_response(404, {"error": f"No session found for session_key '{session_key}'"})

    session = data[0]
    return _json_response(200, {
        "sessionKey": session_key,
        "sessionName": session.get("session_name"),
        "sessionType": session.get("session_type"),
        "dateStart": session.get("date_start"),
        "dateEnd": session.get("date_end"),
        "location": session.get("location"),
        "countryName": session.get("country_name"),
        "circuitShortName": session.get("circuit_short_name"),
        "year": session.get("year"),
    })
