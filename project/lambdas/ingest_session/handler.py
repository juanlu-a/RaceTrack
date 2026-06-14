"""
Lambda for API Gateway (HTTP API):
  GET /ingest?session_key=...

Thin, fast entrypoint. It only validates the request and fires an EventBridge
`IngestRequested` event, then returns 202 immediately. The actual heavy work
(fetching everything from OpenF1, saving to S3, firing SessionIngested) is done
asynchronously by ingest_worker, which is not bound by the API Gateway 30s
integration timeout.

Flow:
  API Gateway -> ingest_session (202) -> EventBridge(IngestRequested)
              -> ingest_worker -> S3 + EventBridge(SessionIngested)
              -> save_session -> RDS
"""
import json
import os

import boto3

EVENTS_ENDPOINT = os.environ.get("EVENTS_ENDPOINT", "")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def _events_client():
    kwargs = {"region_name": AWS_REGION}
    if EVENTS_ENDPOINT:
        # LocalStack mode: use dummy creds + custom endpoint
        kwargs.update({"aws_access_key_id": "test", "aws_secret_access_key": "test", "endpoint_url": EVENTS_ENDPOINT})
    return boto3.client("events", **kwargs)


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

    # Fire the async ingestion request and return immediately.
    try:
        eb = _events_client()
        eb.put_events(Entries=[{
            "Source": "racetrack",
            "DetailType": "IngestRequested",
            "Detail": json.dumps({"session_key": session_key}),
        }])
    except Exception as e:
        return _json_response(500, {
            "error": "Failed to queue ingestion request",
            "details": str(e),
        })

    return _json_response(202, {
        "status": "accepted",
        "session_key": session_key,
        "message": "Ingestion started. Data will be available shortly.",
    })
