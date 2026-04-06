"""
Lambda for API Gateway (HTTP API):
  GET /session?session_key=...  → Returns session details from OpenF1 for a given session key
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


def _extract_session_key(event: dict) -> str:
    params = event.get("queryStringParameters") or {}
    return (params.get("session_key") or "").strip()


def _normalize_session(item: dict) -> dict:
    return {field: item.get(field) for field in SESSION_FIELDS}


def handler(event, context):
    method = _extract_method(event)
    if method and method != "GET":
        return _json_response(405, {"error": "Method not allowed. Use GET"})

    session_key = _extract_session_key(event)
    if not session_key:
        return _json_response(400, {
            "error": "Missing query parameter: session_key",
            "example": "?session_key=9158",
        })

    url = f"{OPENF1_SESSIONS_URL}?session_key={session_key}"
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

    if not isinstance(data, list) or len(data) == 0:
        return _json_response(404, {"error": f"No session found for session_key '{session_key}'"})

    session = data[0] if isinstance(data[0], dict) else {}
    if not session:
        return _json_response(500, {"error": "Unexpected OpenF1 session payload"})

    return _json_response(200, _normalize_session(session))
