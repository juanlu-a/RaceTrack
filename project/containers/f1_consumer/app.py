"""
f1-consumer: long-running SQS → DynamoDB worker.

Long-polls the simulation SQS queue. For each bucket message it computes
per-driver metrics (see metrics.py) and writes one DynamoDB item per bucket,
plus an idempotent META item per simulation. Messages are deleted only on
success; the queue's redrive policy (maxReceiveCount=3) routes poison messages
to the DLQ.

DynamoDB single-table layout (see terraform/dynamodb.tf):
    PK = SIM#<simulation_id>
    SK = META                       -> simulation summary
    SK = BUCKET#<bucket_index:06d>  -> one item per bucket

Config (env):
    SQS_QUEUE_URL        (required) URL of the simulation queue
    DYNAMODB_TABLE       (required) metrics table name
    AWS_DEFAULT_REGION   (default us-east-1)
    SQS_ENDPOINT         optional override (LocalStack)
    DYNAMODB_ENDPOINT    optional override (LocalStack)
    TTL_DAYS             (default 7) auto-expire simulations
    WAIT_TIME_SECONDS    (default 20) SQS long-poll wait
"""
import decimal
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone

import boto3

from metrics import compute_bucket_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("f1_consumer")

AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "")
SQS_ENDPOINT = os.environ.get("SQS_ENDPOINT", "")
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "")
TTL_DAYS = int(os.environ.get("TTL_DAYS", "7"))
WAIT_TIME_SECONDS = int(os.environ.get("WAIT_TIME_SECONDS", "20"))
MAX_MESSAGES = 10

_running = True


def _to_dynamo(value):
    """Recursively convert floats to Decimal (DynamoDB rejects float)."""
    if isinstance(value, float):
        # round-trip through str so we get an exact Decimal, not binary noise
        return decimal.Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    return value


def _sqs_client():
    kwargs = {"region_name": AWS_REGION}
    if SQS_ENDPOINT:
        kwargs.update(aws_access_key_id="test", aws_secret_access_key="test", endpoint_url=SQS_ENDPOINT)
    return boto3.client("sqs", **kwargs)


def _dynamo_table():
    kwargs = {"region_name": AWS_REGION}
    if DYNAMODB_ENDPOINT:
        kwargs.update(aws_access_key_id="test", aws_secret_access_key="test", endpoint_url=DYNAMODB_ENDPOINT)
    return boto3.resource("dynamodb", **kwargs).Table(DYNAMODB_TABLE)


def _put_bucket(table, body, drivers):
    simulation_id = body["simulation_id"]
    bucket_index = int(body["bucket_index"])
    ttl = int(time.time()) + TTL_DAYS * 86400
    item = {
        "PK": f"SIM#{simulation_id}",
        "SK": f"BUCKET#{bucket_index:06d}",
        "bucket_index": bucket_index,
        "race_time_start_seconds": body.get("race_time_start_seconds"),
        "race_time_end_seconds": body.get("race_time_end_seconds"),
        "event_count": body.get("event_count"),
        "bucket_start_timestamp": body.get("bucket_start_timestamp"),
        "drivers": drivers,
        "ttl": ttl,
    }
    table.put_item(Item=_to_dynamo(item))


def _upsert_meta(table, body):
    """Idempotent META upsert. Safe under SQS at-least-once redelivery:
    total_buckets and max_race_time_seconds use max()-style updates, never ADD.
    """
    simulation_id = body["simulation_id"]
    bucket_index = int(body["bucket_index"])
    now = datetime.now(timezone.utc).isoformat()
    candidate_total = bucket_index + 1
    candidate_max_race = body.get("race_time_end_seconds") or 0
    sim_duration = body.get("simulation_duration_seconds")

    # Ensure the META item exists and bump updated_at. Identity fields use
    # if_not_exists so reprocessing never rewrites them. total_buckets and
    # max_race_time_seconds are raised separately by _meta_maxes() (max-style),
    # so this update carries no monotonic counters.
    table.update_item(
        Key={"PK": f"SIM#{simulation_id}", "SK": "META"},
        UpdateExpression=(
            "SET session_id = if_not_exists(session_id, :sid), "
            "simulation_duration_seconds = if_not_exists(simulation_duration_seconds, :dur), "
            "created_at = if_not_exists(created_at, :now), "
            "updated_at = :now"
        ),
        ExpressionAttributeValues=_to_dynamo({
            ":sid": body.get("session_id"),
            ":dur": sim_duration,
            ":now": now,
        }),
    )
    _meta_maxes(table, simulation_id, candidate_total, candidate_max_race)


def _meta_maxes(table, simulation_id, candidate_total, candidate_max_race):
    """Raise total_buckets / max_race_time_seconds to the candidate if larger.

    Two conditional UpdateItems; each is a no-op when the stored value already
    dominates, so reprocessing the same bucket never inflates the counters.
    """
    key = {"PK": f"SIM#{simulation_id}", "SK": "META"}
    for attr, candidate in (
        ("total_buckets", candidate_total),
        ("max_race_time_seconds", candidate_max_race),
    ):
        try:
            table.update_item(
                Key=key,
                UpdateExpression=f"SET {attr} = :c",
                ConditionExpression=f"attribute_not_exists({attr}) OR {attr} < :c",
                ExpressionAttributeValues=_to_dynamo({":c": candidate}),
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            pass  # stored value already >= candidate; nothing to do


def process_message(table, message):
    body = json.loads(message["Body"])
    drivers = compute_bucket_metrics(body)
    _put_bucket(table, body, drivers)
    _upsert_meta(table, body)
    log.info(
        "processed sim=%s bucket=%s drivers=%d events=%s",
        body.get("simulation_id"), body.get("bucket_index"), len(drivers), body.get("event_count"),
    )


def _handle_signal(signum, frame):
    global _running
    log.info("received signal %s, shutting down after current batch", signum)
    _running = False


def main():
    if not SQS_QUEUE_URL or not DYNAMODB_TABLE:
        raise SystemExit("SQS_QUEUE_URL and DYNAMODB_TABLE are required")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    sqs = _sqs_client()
    table = _dynamo_table()
    log.info("f1-consumer started: queue=%s table=%s", SQS_QUEUE_URL, DYNAMODB_TABLE)

    while _running:
        resp = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=MAX_MESSAGES,
            WaitTimeSeconds=WAIT_TIME_SECONDS,
        )
        for message in resp.get("Messages", []):
            try:
                process_message(table, message)
                sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])
            except Exception:
                # leave the message on the queue; SQS redrives to the DLQ after 3 tries
                log.exception("failed to process message %s", message.get("MessageId"))


if __name__ == "__main__":
    main()
