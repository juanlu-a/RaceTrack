"""
Lambda for API Gateway (HTTP API):
  GET /drivers?session_key=...  → Always fetches from OpenF1 and saves to DynamoDB
  GET /cache?session_key=...    → Reads from DynamoDB what was previously saved
"""
import json
import os
from datetime import datetime, timezone

import boto3
import requests

_endpoint = os.environ.get("DYNAMODB_ENDPOINT")
if _endpoint:
    # Local dev: hardcode dummy credentials so DynamoDB Local doesn't reject the
    # expired/real SSO token that SAM injects into the container env vars.
    dynamodb = boto3.resource(
        "dynamodb",
        endpoint_url=_endpoint,
        aws_access_key_id="DUMMYIDEXAMPLE",
        aws_secret_access_key="dummysecretkey",
        aws_session_token=None,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-2"),
    )
else:
    dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME")


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _get_session_key(event: dict) -> str:
    params = event.get("queryStringParameters") or {}
    return (params.get("session_key") or "").strip()


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


def _import_drivers(session_key: str) -> dict:
    """Always fetch from OpenF1, save to DynamoDB, return import result."""
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
    now = datetime.now(timezone.utc).isoformat()

    try:
        dynamodb.Table(TABLE_NAME).put_item(Item={
            "session_key": session_key,
            "pilots": pilots,
            "pilot_count": len(pilots),
            "saved_at": now,
        })
    except Exception as e:
        return _json_response(500, {"error": "Error writing to DynamoDB", "details": str(e)})

    return _json_response(200, {
        "message": "Data imported successfully",
        "sessionKey": session_key,
        "pilotCount": len(pilots),
        "pilots": pilots,
        "savedAt": now,
    })


def _get_from_cache(session_key: str) -> dict:
    """Read session data from DynamoDB."""
    try:
        resp = dynamodb.Table(TABLE_NAME).get_item(Key={"session_key": session_key})
    except Exception as e:
        return _json_response(500, {"error": "Error reading DynamoDB", "details": str(e)})

    if "Item" not in resp:
        return _json_response(404, {
            "error": f"No data found for session_key '{session_key}'",
            "hint": f"Call GET /drivers?session_key={session_key} first to import the data",
        })

    item = resp["Item"]
    return _json_response(200, {
        "sessionKey": session_key,
        "pilots": item.get("pilots", []),
        "pilotCount": int(item.get("pilot_count", 0)),
        "savedAt": item.get("saved_at"),
    })


def handler(event, context):
    if not TABLE_NAME:
        return _json_response(500, {"error": "TABLE_NAME is not configured"})

    session_key = _get_session_key(event)
    if not session_key:
        return _json_response(400, {
            "error": "Missing query parameter: session_key",
            "example": "?session_key=9159",
        })

    route = event.get("routeKey", "")

    if "GET /drivers" in route:
        return _import_drivers(session_key)
    elif "GET /cache" in route:
        return _get_from_cache(session_key)
    else:
        return _json_response(404, {"error": f"Unknown route: {route}"})
