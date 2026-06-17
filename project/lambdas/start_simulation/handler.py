"""
Lambda for API Gateway (HTTP API):
  POST /start-simulation

Reads the chronological `session_events` for a session (populated by
save_session), groups them into fixed 10-second windows of *race time*
("buckets"), and publishes ONE SQS message per bucket to an SQS Standard queue.

Each bucket message carries all the events that occurred in that 10s window,
so thousands of raw events collapse into a handful of ordered messages.

DelaySeconds is used only for ordering / throttling (NOT to simulate the real
race duration): the bucket at chronological position k is published with
DelaySeconds = min(900, k * DELAY_STEP_SECONDS) using a fixed 1s step.
900s is the AWS hard cap.

Messages are sent in batches of up to 10 (send_message_batch) purely as a
transport optimization; the content of each message is unchanged.

This is a publisher only; no consumer is implemented here.
"""
import base64
import json
import os
import uuid
from datetime import timedelta

import boto3
import psycopg2
import psycopg2.extras

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "racetrack")
DB_USER = os.environ.get("DB_USER", "racetrack")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "racetrack")

AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
# Optional override to point at a custom endpoint (e.g. LocalStack) in the
# future. Not wired into any local tooling today; real AWS is used by default.
SQS_ENDPOINT = os.environ.get("SQS_ENDPOINT", "")

BUCKET_SECONDS = 10
# Fixed step (seconds) between consecutive buckets, used only for
# ordering/throttling: the bucket at chronological position k is published with
# DelaySeconds = min(900, k * DELAY_STEP_SECONDS). NOT the real race duration.
DELAY_STEP_SECONDS = 1
# AWS hard cap for SQS DelaySeconds (15 minutes).
MAX_DELAY_SECONDS = 900
# SQS allows at most 10 entries per send_message_batch call.
SQS_BATCH_SIZE = 10


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
    )


def _sqs_client():
    kwargs = {"region_name": AWS_REGION}
    if SQS_ENDPOINT:
        # Optional override (e.g. LocalStack): use dummy creds + custom endpoint.
        kwargs.update({"aws_access_key_id": "test", "aws_secret_access_key": "test", "endpoint_url": SQS_ENDPOINT})
    return boto3.client("sqs", **kwargs)


def _parse_body(event) -> dict:
    """Parse the HTTP API v2 body, handling JSON strings and base64."""
    raw = event.get("body")
    if raw is None:
        return {}
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    raise ValueError("Unsupported body type")


def _build_buckets(rows):
    """Group ordered rows into 10s race-time buckets keyed by bucket_index.

    Returns (t0, ordered_list_of_(bucket_index, events)).
    """
    t0 = rows[0]["timestamp"]
    buckets = {}
    for r in rows:
        ts = r["timestamp"]
        bucket_index = int((ts - t0).total_seconds() // BUCKET_SECONDS)
        buckets.setdefault(bucket_index, []).append({
            "event_type": r["event_type"],
            "driver_id": r["driver_id"],
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else ts,
            "payload": r["payload"],
        })
    ordered = sorted(buckets.items(), key=lambda kv: kv[0])
    return t0, ordered


def handler(event, context):
    try:
        body = _parse_body(event)
    except (ValueError, json.JSONDecodeError):
        return _json_response(400, {"error": "Invalid JSON body"})

    session_id = body.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return _json_response(400, {
            "error": "Missing or invalid field: session_id (non-empty string required)",
            "example": {"session_id": "9158", "simulation_duration_seconds": 300},
        })
    session_id = session_id.strip()

    # Metadata only: does not affect publishing.
    simulation_duration_seconds = body.get("simulation_duration_seconds")

    if not SQS_QUEUE_URL:
        return _json_response(500, {"error": "SQS_QUEUE_URL is not configured"})

    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT event_type, driver_id, payload, "timestamp"
                FROM session_events
                WHERE session_id = %s
                ORDER BY "timestamp" ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return _json_response(500, {"error": "Failed to query RDS", "details": str(e)})

    if not rows:
        return _json_response(404, {
            "error": f"No session_events found for session '{session_id}'",
            "hint": f"Run GET /ingest?session_key={session_id} first",
        })

    t0, ordered_buckets = _build_buckets(rows)
    simulation_id = str(uuid.uuid4())

    # Build one SQS entry per bucket; chronological position k drives DelaySeconds.
    entries = []
    events_total = 0
    for k, (bucket_index, events) in enumerate(ordered_buckets):
        delay_seconds = min(MAX_DELAY_SECONDS, k * DELAY_STEP_SECONDS)
        bucket_start = t0 + timedelta(seconds=bucket_index * BUCKET_SECONDS)
        bucket_end = bucket_start + timedelta(seconds=BUCKET_SECONDS)
        events_total += len(events)

        message_body = {
            "simulation_id": simulation_id,
            "session_id": session_id,
            "bucket_index": bucket_index,
            "race_time_start_seconds": bucket_index * BUCKET_SECONDS,
            "race_time_end_seconds": (bucket_index + 1) * BUCKET_SECONDS,
            "bucket_start_timestamp": bucket_start.isoformat(),
            "bucket_end_timestamp": bucket_end.isoformat(),
            "delay_seconds": delay_seconds,
            "simulation_duration_seconds": simulation_duration_seconds,
            "event_count": len(events),
            "events": events,
        }
        entries.append({
            "Id": str(k),
            "MessageBody": json.dumps(message_body, default=str),
            "DelaySeconds": delay_seconds,
        })

    try:
        sqs = _sqs_client()
        failed = []
        for i in range(0, len(entries), SQS_BATCH_SIZE):
            chunk = entries[i:i + SQS_BATCH_SIZE]
            resp = sqs.send_message_batch(QueueUrl=SQS_QUEUE_URL, Entries=chunk)
            failed.extend(resp.get("Failed", []))
    except Exception as e:
        return _json_response(500, {"error": "Failed to publish to SQS", "details": str(e)})

    if failed:
        return _json_response(500, {
            "error": "Some bucket messages failed to publish",
            "simulation_id": simulation_id,
            "failed_count": len(failed),
            "details": failed,
        })

    return _json_response(202, {
        "simulation_id": simulation_id,
        "session_id": session_id,
        "buckets_published": len(entries),
        "events_total": events_total,
    })
