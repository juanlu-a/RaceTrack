"""
Lambda for API Gateway (HTTP API):
  GET /sessions[?year=...]  -> Returns all F1 sessions from OpenF1
"""
import json

import requests

OPENF1_SESSIONS_URL = "https://api.openf1.org/v1/sessions"
SESSION_FIELDS = [
    "circuit_key",
    "circuit_short_name",
    "country_code",
    "country_key",
    "country_name",
    "date_end",
    "date_start",
    "gmt_offset",
    "location",
    "meeting_key",
    "session_key",
    "session_name",
    "session_type",
    "year",
]


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _extract_method(event: dict) -> str:
    return (event.get("requestContext", {}).get("http", {}).get("method") or "").upper()


def _normalize_session(item: dict) -> dict:
    return {field: item.get(field) for field in SESSION_FIELDS}


def handler(event, context):
    method = _extract_method(event)
    if method and method != "GET":
        return _json_response(405, {"error": "Method not allowed. Use GET"})

    params = event.get("queryStringParameters") or {}
    year = (params.get("year") or "").strip()
    if year and not year.isdigit():
        return _json_response(400, {
            "error": "Invalid query parameter: year must be numeric",
            "example": "?year=2023",
        })

    url = f"{OPENF1_SESSIONS_URL}?year={year}" if year else OPENF1_SESSIONS_URL
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.Timeout:
        return _json_response(502, {"error": "OpenF1 API timeout"})
    except requests.exceptions.RequestException as e:
        return _json_response(502, {"error": "Failed to call OpenF1 API", "details": str(e)})
    except ValueError:
        return _json_response(502, {"error": "OpenF1 returned invalid JSON"})

    if not isinstance(data, list):
        return _json_response(502, {"error": "Unexpected response from OpenF1 API"})
    if year and len(data) == 0:
        return _json_response(404, {"error": f"No sessions found for year '{year}'"})

    sessions = [_normalize_session(s) for s in data if isinstance(s, dict)]
    return _json_response(
        200,
        {
            "count": len(sessions),
            "year": int(year) if year else None,
            "sessions": sessions,
        },
    )
