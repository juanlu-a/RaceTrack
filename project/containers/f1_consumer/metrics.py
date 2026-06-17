"""
Pure, dependency-free metric computation for the f1-consumer.

Given one SQS bucket message body (see start_simulation/handler.py), reduce the
raw events in that 10s race-time window into per-driver metrics. No boto3, no
I/O — everything here is a pure function so it can be unit-tested in isolation.

Telemetry is NOT averaged: we take the *current* (last in the bucket) value and,
for speed, also the max. Events within a bucket are assumed roughly ordered, but
we sort defensively by timestamp so "last" is well defined.

Per-driver metric keys produced:
    speed_kmh, max_speed_kmh, x, y, gap_to_leader_seconds, position,
    lap_number, last_lap_duration, is_pit_out_lap
Keys are only present when the corresponding event type appeared in the bucket.
"""
from typing import Any, Dict, List, Optional


def _event_ts(event: Dict[str, Any]) -> str:
    # ISO 8601 strings sort chronologically as plain strings.
    return event.get("timestamp") or ""


def _last(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the chronologically last event, or None for an empty list."""
    if not events:
        return None
    return max(events, key=_event_ts)


def _num(value: Any) -> Optional[float]:
    """Coerce to float, tolerating None / bad data without raising."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_driver_metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the metric map for a single driver's events within one bucket.

    `events` are the bucket events already filtered to one driver_id, each shaped
    like {"event_type", "driver_id", "timestamp", "payload"}.
    """
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events:
        by_type.setdefault(ev.get("event_type"), []).append(ev)

    metrics: Dict[str, Any] = {}

    # speed (current = last, plus max) from car_data
    car_data = by_type.get("car_data", [])
    speeds = [s for s in (_num((e.get("payload") or {}).get("speed")) for e in car_data) if s is not None]
    if speeds:
        last_car = _last(car_data)
        current_speed = _num((last_car.get("payload") or {}).get("speed"))
        if current_speed is not None:
            metrics["speed_kmh"] = current_speed
        metrics["max_speed_kmh"] = max(speeds)

    # position on track (x, y) from the last location point
    last_loc = _last(by_type.get("location", []))
    if last_loc is not None:
        payload = last_loc.get("payload") or {}
        x, y = _num(payload.get("x")), _num(payload.get("y"))
        if x is not None:
            metrics["x"] = x
        if y is not None:
            metrics["y"] = y

    # gap to leader from the last interval event
    last_interval = _last(by_type.get("interval", []))
    if last_interval is not None:
        gap = _num((last_interval.get("payload") or {}).get("gap_to_leader"))
        if gap is not None:
            metrics["gap_to_leader_seconds"] = gap

    # race position (ranking) from the last position event
    last_position = _last(by_type.get("position", []))
    if last_position is not None:
        pos = (last_position.get("payload") or {}).get("position")
        pos_num = _num(pos)
        if pos_num is not None:
            metrics["position"] = int(pos_num)

    # lap info from the last lap event
    last_lap = _last(by_type.get("lap", []))
    if last_lap is not None:
        payload = last_lap.get("payload") or {}
        lap_number = _num(payload.get("lap_number"))
        if lap_number is not None:
            metrics["lap_number"] = int(lap_number)
        last_lap_duration = _num(payload.get("lap_duration"))
        if last_lap_duration is not None:
            metrics["last_lap_duration"] = last_lap_duration
        if "is_pit_out_lap" in payload:
            metrics["is_pit_out_lap"] = bool(payload.get("is_pit_out_lap"))

    return metrics


def compute_bucket_metrics(message_body: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a full bucket message into the DynamoDB `drivers` map.

    Returns {"<driver_id>": {<metrics>}, ...}. driver_id keys are stringified
    because DynamoDB map keys must be strings; None driver_ids are skipped.
    """
    events = message_body.get("events") or []
    by_driver: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events:
        driver_id = ev.get("driver_id")
        if driver_id is None:
            continue
        by_driver.setdefault(str(driver_id), []).append(ev)

    return {
        driver_id: compute_driver_metrics(driver_events)
        for driver_id, driver_events in by_driver.items()
    }
