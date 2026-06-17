"""
Lambda triggered by EventBridge:
  Source: racetrack
  DetailType: IngestRequested
  Detail: { "session_key": "..." }

This is the heavy ingestion worker. It runs asynchronously (no API Gateway 30s
limit) so it can pull everything for a session from OpenF1 (session metadata,
all drivers, laps, position and the high-frequency telemetry), bundle it into a
single JSON payload, save it to S3, then fire a `SessionIngested` EventBridge
event so save_session can persist everything to RDS.

The thin HTTP lambda (ingest_session) only validates the request and fires the
`IngestRequested` event, returning 202 immediately. All the slow work lives here.

Fetch optimizations vs a naive per-driver loop:
  - laps and position are fetched ONCE per session (no driver_number) instead of
    one call per driver.
  - car_data is filtered server-side to moving points (speed>=1) and clipped to
    the race window, which removes the large stationary/garage stretches.
  - location has no speed field, so we derive the "moving" time intervals from
    the car_data timestamps (gaps > MOVING_GAP_SECONDS split runs) and fetch
    location only inside those intervals.

car_data and location are still decimated to ~TELEMETRY_SAMPLE_HZ (default 1 Hz)
to keep volume sane. No averaging — original values are kept.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import boto3
import requests

OPENF1_BASE = "https://api.openf1.org/v1"

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "racetrack-sessions")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
EVENTS_ENDPOINT = os.environ.get("EVENTS_ENDPOINT", "")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# Telemetry decimation: keep at most one car_data/location point per
# (1 / TELEMETRY_SAMPLE_HZ) seconds, per driver. Set <= 0 to keep every point.
try:
    TELEMETRY_SAMPLE_HZ = float(os.environ.get("TELEMETRY_SAMPLE_HZ", "1"))
except ValueError:
    TELEMETRY_SAMPLE_HZ = 1.0
TELEMETRY_MIN_INTERVAL_SECONDS = (1.0 / TELEMETRY_SAMPLE_HZ) if TELEMETRY_SAMPLE_HZ > 0 else 0.0

# A gap larger than this (seconds) between consecutive moving car_data points is
# treated as the car being parked (in the garage / between runs), splitting one
# continuous "run" from the next. Used to build the location fetch intervals.
try:
    MOVING_GAP_SECONDS = float(os.environ.get("MOVING_GAP_SECONDS", "30"))
except ValueError:
    MOVING_GAP_SECONDS = 30.0

# Seconds of padding added to each side of a moving interval when querying
# location, so we don't clip the very start/end of a run.
MOVING_PAD_SECONDS = 5


def _s3_client():
    kwargs = {"region_name": AWS_REGION}
    if S3_ENDPOINT:
        # LocalStack mode: use dummy creds + custom endpoint
        kwargs.update({"aws_access_key_id": "test", "aws_secret_access_key": "test", "endpoint_url": S3_ENDPOINT})
    return boto3.client("s3", **kwargs)


def _events_client():
    kwargs = {"region_name": AWS_REGION}
    if EVENTS_ENDPOINT:
        kwargs.update({"aws_access_key_id": "test", "aws_secret_access_key": "test", "endpoint_url": EVENTS_ENDPOINT})
    return boto3.client("events", **kwargs)


def _fetch(path: str, params: dict) -> list:
    url = f"{OPENF1_BASE}/{path}"
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected response from OpenF1 {path}: {type(data)}")
    return data


def _fetch_optional(path: str, params: dict) -> list:
    """Best-effort fetch: returns [] instead of raising if the dataset is
    missing or the call fails (some sessions don't expose every dataset)."""
    try:
        return _fetch(path, params)
    except (requests.exceptions.RequestException, ValueError):
        return []


def _parse_dt(value):
    """Parse an OpenF1 ISO timestamp into a tz-aware UTC datetime, or None."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _openf1_date(dt) -> str:
    """Format a datetime as the second-resolution ISO string OpenF1 accepts in
    its date>= / date<= filters."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _window_params(start_dt, end_dt) -> dict:
    """Build OpenF1 date-window query params. requests urlencodes the operator
    char (`>` -> %3E, `<` -> %3C), which OpenF1 accepts, so `{"date>": x}` is
    sent as `date>=x` and `{"date<": y}` as `date<=y`."""
    params = {}
    if start_dt is not None and end_dt is not None and end_dt > start_dt:
        params["date>"] = _openf1_date(start_dt)
        params["date<"] = _openf1_date(end_dt)
    return params


def _moving_intervals(points, gap_seconds, pad_seconds):
    """Cluster moving car_data points into continuous runs.

    Points are sorted by `date`; a gap larger than `gap_seconds` starts a new
    run. Each run is returned as a (start_dt, end_dt) tuple padded by
    `pad_seconds` on each side. Returns [] if there are no usable timestamps.
    """
    times = sorted(dt for dt in (_parse_dt(p.get("date")) for p in points) if dt is not None)
    if not times:
        return []

    runs = []
    run_start = run_end = times[0]
    for dt in times[1:]:
        if (dt - run_end).total_seconds() > gap_seconds:
            runs.append((run_start, run_end))
            run_start = dt
        run_end = dt
    runs.append((run_start, run_end))

    pad = timedelta(seconds=pad_seconds)
    return [(s - pad, e + pad) for s, e in runs]


def _reduce_telemetry(points, keep_fields, start_dt, end_dt, min_interval_seconds):
    """Decimate high-frequency telemetry without averaging.

    Sorts the points by their `date`, clips them to the race window
    [start_dt, end_dt] (only when both bounds are valid and end > start), and
    keeps at most one point per `min_interval_seconds`. Each kept point is
    projected down to `keep_fields` (original values preserved).
    """
    parsed = []
    for p in points:
        if not isinstance(p, dict):
            continue
        dt = _parse_dt(p.get("date"))
        if dt is None:
            continue
        parsed.append((dt, p))
    parsed.sort(key=lambda t: t[0])

    apply_window = start_dt is not None and end_dt is not None and end_dt > start_dt

    reduced = []
    last_kept = None
    for dt, p in parsed:
        if apply_window and not (start_dt <= dt <= end_dt):
            continue
        if (
            last_kept is not None
            and min_interval_seconds > 0
            and (dt - last_kept).total_seconds() < min_interval_seconds
        ):
            continue
        last_kept = dt
        reduced.append({k: p.get(k) for k in keep_fields})
    return reduced


def _resolve_session_key(event) -> str:
    """Accept either an EventBridge event (detail.session_key) or a direct
    invoke with queryStringParameters (handy for `make invoke-worker`)."""
    detail = event.get("detail") or {}
    session_key = str(detail.get("session_key") or "").strip()
    if session_key:
        return session_key
    params = event.get("queryStringParameters") or {}
    return (params.get("session_key") or "").strip()


def handler(event, context):
    session_key = _resolve_session_key(event)
    if not session_key:
        return {"statusCode": 400, "body": json.dumps({
            "error": "Missing session_key in event detail",
        })}

    # 1. Fetch the required datasets (a failure here aborts ingestion).
    try:
        sessions = _fetch("sessions", {"session_key": session_key})
        drivers = _fetch("drivers", {"session_key": session_key})
    except requests.exceptions.Timeout:
        return {"statusCode": 502, "body": json.dumps({"error": "OpenF1 API timeout"})}
    except requests.exceptions.RequestException as e:
        return {"statusCode": 502, "body": json.dumps({"error": "Failed to call OpenF1 API", "details": str(e)})}
    except ValueError as e:
        return {"statusCode": 502, "body": json.dumps({"error": str(e)})}

    if not sessions:
        return {"statusCode": 404, "body": json.dumps({
            "error": f"No session found for session_key '{session_key}'",
        })}

    race_start_dt = _parse_dt(sessions[0].get("date_start"))
    race_end_dt = _parse_dt(sessions[0].get("date_end"))
    window = _window_params(race_start_dt, race_end_dt)

    # 2. Session-wide datasets. laps and position return ALL drivers in one call
    #    (no driver_number), so we avoid the per-driver loop entirely. The rest
    #    are best-effort (some sessions don't expose every dataset).
    laps = _fetch_optional("laps", {"session_key": session_key})
    position = _fetch_optional("position", {"session_key": session_key})
    starting_grid = _fetch_optional("starting_grid", {"session_key": session_key})
    pit = _fetch_optional("pit", {"session_key": session_key})
    intervals = _fetch_optional("intervals", {"session_key": session_key})
    race_control = _fetch_optional("race_control", {"session_key": session_key})

    # 3. Per-driver telemetry. car_data is filtered server-side to moving points
    #    (speed>=1) inside the race window; the resulting timestamps define the
    #    intervals we use to fetch location (which has no speed field).
    car_data = []
    location = []
    for d in drivers:
        driver_number = d.get("driver_number")
        if driver_number is None:
            continue

        car_params = {"session_key": session_key, "driver_number": driver_number, "speed>": 1}
        car_params.update(window)
        raw_car_data = _fetch_optional("car_data", car_params)
        car_data.extend(_reduce_telemetry(
            raw_car_data,
            keep_fields=["date", "driver_number", "speed"],
            start_dt=race_start_dt,
            end_dt=race_end_dt,
            min_interval_seconds=TELEMETRY_MIN_INTERVAL_SECONDS,
        ))

        # Fetch location only for the intervals where the car was moving.
        raw_location = []
        for s_dt, e_dt in _moving_intervals(raw_car_data, MOVING_GAP_SECONDS, MOVING_PAD_SECONDS):
            loc_params = {"session_key": session_key, "driver_number": driver_number}
            loc_params.update(_window_params(s_dt, e_dt))
            raw_location.extend(_fetch_optional("location", loc_params))
        location.extend(_reduce_telemetry(
            raw_location,
            keep_fields=["date", "driver_number", "x", "y", "z"],
            start_dt=race_start_dt,
            end_dt=race_end_dt,
            min_interval_seconds=TELEMETRY_MIN_INTERVAL_SECONDS,
        ))

    payload = {
        "session_key": session_key,
        "session": sessions[0],
        "drivers": drivers,
        "starting_grid": starting_grid,
        "laps": laps,
        "pit": pit,
        "position": position,
        "intervals": intervals,
        "race_control": race_control,
        "car_data": car_data,
        "location": location,
    }

    # 4. Save raw JSON to S3
    s3_key = f"sessions/{session_key}/raw.json"
    try:
        s3 = _s3_client()
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
        return {"statusCode": 500, "body": json.dumps({"error": "Failed to save to S3", "details": str(e)})}

    # 5. Fire EventBridge event so save_session can pick it up
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
        return {"statusCode": 500, "body": json.dumps({
            "error": "Saved to S3 but failed to fire EventBridge event",
            "details": str(e),
            "s3_key": s3_key,
        })}

    return {"statusCode": 200, "body": json.dumps({
        "message": "Session ingested successfully",
        "session_key": session_key,
        "drivers_fetched": len(drivers),
        "starting_grid_fetched": len(starting_grid),
        "laps_fetched": len(laps),
        "pit_fetched": len(pit),
        "position_fetched": len(position),
        "intervals_fetched": len(intervals),
        "race_control_fetched": len(race_control),
        "car_data_points": len(car_data),
        "location_points": len(location),
    })}
