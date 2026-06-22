"""
metrics-exporter: owns the simulation clock, serves Prometheus /metrics.

Periodically reads a simulation's buckets from DynamoDB (single Query, ordered by
the BUCKET#<padded> SK), advances an in-memory simulation clock, and publishes the
currently-applicable bucket's per-driver metrics as Prometheus gauges (pull model).

Clock logic lives in clock.py (pure, tested). This module wires it to DynamoDB,
the prometheus_client HTTP server, and the wall clock.

Config (env):
    DYNAMODB_TABLE       (required) metrics table name
    AWS_DEFAULT_REGION   (default us-east-1)
    DYNAMODB_ENDPOINT    optional override (LocalStack)
    SIMULATION_ID        pin a specific simulation; otherwise newest META wins
    METRICS_PORT         (default 9100)
    REFRESH_SECONDS      (default 5) DynamoDB Query + gauge update interval
"""
import logging
import os
import time
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from prometheus_client import Gauge, start_http_server

from clock import is_complete, progress_ratio, select_bucket, sim_race_time_seconds, speed_factor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("metrics_exporter")

AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "")
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "")
SIMULATION_ID = os.environ.get("SIMULATION_ID", "")
METRICS_PORT = int(os.environ.get("METRICS_PORT", "9100"))
REFRESH_SECONDS = float(os.environ.get("REFRESH_SECONDS", "5"))

# DynamoDB driver metric key -> Prometheus gauge registry key.
_DRIVER_GAUGES = {
    "speed_kmh": Gauge("f1_driver_speed_kmh", "Current speed (km/h)", ["simulation_id", "driver_id"]),
    "max_speed_kmh": Gauge("f1_driver_max_speed_kmh", "Max speed in bucket (km/h)", ["simulation_id", "driver_id"]),
    "gap_to_leader_seconds": Gauge("f1_driver_gap_to_leader_seconds", "Gap to leader (s)", ["simulation_id", "driver_id"]),
    "position": Gauge("f1_driver_position", "Race position", ["simulation_id", "driver_id"]),
    "lap_number": Gauge("f1_driver_lap_number", "Current lap number", ["simulation_id", "driver_id"]),
    "last_lap_duration": Gauge("f1_driver_last_lap_seconds", "Last lap duration (s)", ["simulation_id", "driver_id"]),
    "x": Gauge("f1_driver_track_x", "Track X coordinate", ["simulation_id", "driver_id"]),
    "y": Gauge("f1_driver_track_y", "Track Y coordinate", ["simulation_id", "driver_id"]),
}

_RACE_TIME_GAUGE = Gauge("f1_simulation_race_time_seconds", "Simulation race time (s)", ["simulation_id"])
_PROGRESS_GAUGE = Gauge("f1_simulation_progress_ratio", "Race progress [0,1]", ["simulation_id"])
_COMPLETE_GAUGE = Gauge("f1_simulation_complete", "1 when simulation race time has finished", ["simulation_id"])


def _table():
    kwargs = {"region_name": AWS_REGION}
    if DYNAMODB_ENDPOINT:
        kwargs.update(aws_access_key_id="test", aws_secret_access_key="test", endpoint_url=DYNAMODB_ENDPOINT)
    return boto3.resource("dynamodb", **kwargs).Table(DYNAMODB_TABLE)


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clear_gauges():
    """Drop stale label combinations so only the active simulation snapshot is exported."""
    for gauge in _DRIVER_GAUGES.values():
        gauge.clear()
    _RACE_TIME_GAUGE.clear()
    _PROGRESS_GAUGE.clear()
    _COMPLETE_GAUGE.clear()


def _find_newest_meta(table):
    """Scan for META items and return the one with the newest created_at."""
    items = []
    kwargs = {"FilterExpression": Key("SK").eq("META")}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    if not items:
        return None
    return max(items, key=lambda m: m.get("created_at", ""))


def _load_simulation(table, simulation_id):
    """Return (meta, ordered_buckets) for a simulation, or (None, []) if absent."""
    meta_resp = table.get_item(Key={"PK": f"SIM#{simulation_id}", "SK": "META"})
    meta = meta_resp.get("Item")
    if not meta:
        return None, []
    buckets = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"SIM#{simulation_id}") & Key("SK").begins_with("BUCKET#"),
    }
    while True:
        resp = table.query(**kwargs)
        buckets.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return meta, buckets


def _publish(simulation_id, bucket, race_time, ratio, complete):
    _clear_gauges()
    _RACE_TIME_GAUGE.labels(simulation_id=simulation_id).set(race_time)
    _PROGRESS_GAUGE.labels(simulation_id=simulation_id).set(ratio)
    _COMPLETE_GAUGE.labels(simulation_id=simulation_id).set(1 if complete else 0)
    if bucket is None:
        return
    drivers = bucket.get("drivers") or {}
    for driver_id, metrics in drivers.items():
        for metric_key, gauge in _DRIVER_GAUGES.items():
            value = _num(metrics.get(metric_key))
            if value is not None:
                gauge.labels(simulation_id=simulation_id, driver_id=str(driver_id)).set(value)


def main():
    if not DYNAMODB_TABLE:
        raise SystemExit("DYNAMODB_TABLE is required")

    table = _table()
    start_http_server(METRICS_PORT)
    log.info("metrics-exporter serving /metrics on :%d table=%s", METRICS_PORT, DYNAMODB_TABLE)

    # Per-simulation wall-clock anchor, fixed the first time a sim is seen.
    sim_starts = {}

    while True:
        try:
            simulation_id = SIMULATION_ID
            if not simulation_id:
                newest = _find_newest_meta(table)
                if newest:
                    simulation_id = newest["PK"].split("#", 1)[1]

            if simulation_id:
                meta, buckets = _load_simulation(table, simulation_id)
                if meta:
                    now = datetime.now(timezone.utc)
                    if simulation_id not in sim_starts:
                        sim_starts[simulation_id] = now
                        log.info("new simulation %s, clock started", simulation_id)
                    elapsed = (now - sim_starts[simulation_id]).total_seconds()

                    max_race = _num(meta.get("max_race_time_seconds")) or 0.0
                    duration = _num(meta.get("simulation_duration_seconds")) or 0.0
                    factor = speed_factor(max_race, duration)
                    race_time = sim_race_time_seconds(elapsed, factor)
                    complete = is_complete(race_time, max_race)
                    if complete and max_race > 0:
                        race_time = max_race
                    ratio = 1.0 if complete else progress_ratio(race_time, max_race)

                    ordered = sorted(buckets, key=lambda b: _num(b.get("race_time_start_seconds")) or 0.0)
                    bucket = select_bucket(ordered, race_time)
                    if complete and ordered:
                        bucket = ordered[-1]
                    _publish(simulation_id, bucket, race_time, ratio, complete)
                    if complete:
                        log.info("simulation %s complete at race_time=%.1fs", simulation_id, race_time)
        except Exception:
            log.exception("refresh failed")

        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
