"""
Lambda for API Gateway (HTTP API):
  GET /ingest?session_key=...

Fetches ALL data for the session from OpenF1 (session info, drivers, laps),
bundles it into a single JSON payload, saves it to S3, then fires an
EventBridge event so save_session can persist everything to RDS.

This is the ONE-TIME ingestion step. After this runs, all other lambdas
read exclusively from RDS — they never call OpenF1 again.
"""
import json
import os

import boto3
import requests

OPENF1_BASE = "https://api.openf1.org/v1"

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "racetrack-sessions")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
EVENTS_ENDPOINT = os.environ.get("EVENTS_ENDPOINT", "")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

_dummy_creds = {
    "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID", "test"),
    "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    "aws_session_token": None,
    "region_name": AWS_REGION,
}


def _s3_client():
    kwargs = dict(_dummy_creds)
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
    return boto3.client("s3", **kwargs)


def _events_client():
    kwargs = dict(_dummy_creds)
    if EVENTS_ENDPOINT:
        kwargs["endpoint_url"] = EVENTS_ENDPOINT
    return boto3.client("events", **kwargs)


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _fetch(path: str, params: dict) -> list:
    url = f"{OPENF1_BASE}/{path}"
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected response from OpenF1 {path}: {type(data)}")
    return data


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    session_key = (params.get("session_key") or "").strip()
    if not session_key:
        return _json_response(400, {
            "error": "Missing query parameter: session_key",
            "example": "?session_key=9158",
        })

    # 1. Fetch everything from OpenF1
    try:
        sessions = _fetch("sessions", {"session_key": session_key})
        drivers = _fetch("drivers", {"session_key": session_key})
        laps = _fetch("laps", {"session_key": session_key})
    except requests.exceptions.Timeout:
        return _json_response(502, {"error": "OpenF1 API timeout"})
    except requests.exceptions.RequestException as e:
        return _json_response(502, {"error": "Failed to call OpenF1 API", "details": str(e)})
    except ValueError as e:
        return _json_response(502, {"error": str(e)})

    if not sessions:
        return _json_response(404, {"error": f"No session found for session_key '{session_key}'"})

    payload = {
        "session_key": session_key,
        "session": sessions[0],
        "drivers": drivers,
        "laps": laps,
    }

    # 2. Save raw JSON to S3
    s3_key = f"sessions/{session_key}/raw.json"
    try:
        s3 = _s3_client()
        # Ensure bucket exists (LocalStack dev convenience)
        try:
            s3.head_bucket(Bucket=S3_BUCKET)
        except Exception:
            s3.create_bucket(Bucket=S3_BUCKET)
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=json.dumps(payload, default=str).encode(),
            ContentType="application/json",
        )
    except Exception as e:
        return _json_response(500, {"error": "Failed to save to S3", "details": str(e)})

    # 3. Fire EventBridge event so save_session can pick it up
    event_detail = json.dumps({
        "bucket": S3_BUCKET,
        "key": s3_key,
        "session_key": session_key,
    })
    try:
        eb = _events_client()
        eb.put_events(Entries=[{
            "Source": "racetrack",
            "DetailType": "SessionIngested",
            "Detail": event_detail,
        }])
    except Exception as e:
        return _json_response(500, {
            "error": "Saved to S3 but failed to fire EventBridge event",
            "details": str(e),
            "s3_key": s3_key,
        })

    return _json_response(200, {
        "message": "Session ingested successfully",
        "session_key": session_key,
        "s3_bucket": S3_BUCKET,
        "s3_key": s3_key,
        "drivers_fetched": len(drivers),
        "laps_fetched": len(laps),
    })
