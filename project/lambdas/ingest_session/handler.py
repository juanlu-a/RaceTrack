"""
Lambda for API Gateway (HTTP API):
  GET /ingest?session_key=...

Fetches the data for the session from OpenF1 (session info, drivers,
starting_grid, laps, pit, position, intervals, race_control, car_data,
location), bundles it into a single JSON payload, saves it to S3, then fires an
EventBridge event so save_session can persist everything to RDS.

car_data and location are high-frequency telemetry (~3-4 Hz per driver). They
are NOT stored raw: they are decimated to ~TELEMETRY_SAMPLE_HZ (default 1 Hz) by
keeping at most one point per time slot, and clipped to the race window
[session.date_start, session.date_end]. No averaging — original values are kept.

This is the ONE-TIME ingestion step. After this runs, all other lambdas
read exclusively from RDS — they never call OpenF1 again.
"""
import json
import os
from datetime import datetime, timezone

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


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    session_key = (params.get("session_key") or "").strip()
    if not session_key:
        return _json_response(400, {
            "error": "Missing query parameter: session_key",
            "example": "?session_key=9158",
        })

    # 1. Fetch the required datasets (a failure here aborts ingestion).
    #    NOTE: car_data and location are intentionally excluded: they are
    #    high-frequency telemetry (millions of rows) that would blow the
    #    Lambda timeout/memory and produce a huge S3 object.
    try:
        sessions = _fetch("sessions", {"session_key": session_key})
        drivers = _fetch("drivers", {"session_key": session_key})
    except requests.exceptions.Timeout:
        return _json_response(502, {"error": "OpenF1 API timeout"})
    except requests.exceptions.RequestException as e:
        return _json_response(502, {"error": "Failed to call OpenF1 API", "details": str(e)})
    except ValueError as e:
        return _json_response(502, {"error": str(e)})

    if not sessions:
        return _json_response(404, {"error": f"No session found for session_key '{session_key}'"})

    # 2. Fetch optional session-wide datasets. These are best-effort: some
    #    sessions don't expose every dataset (e.g. starting_grid 404s for
    #    practice/qualifying), so a failure defaults to an empty list.
    starting_grid = _fetch_optional("starting_grid", {"session_key": session_key})
    pit = _fetch_optional("pit", {"session_key": session_key})
    intervals = _fetch_optional("intervals", {"session_key": session_key})
    race_control = _fetch_optional("race_control", {"session_key": session_key})

    # 3. Fetch per-driver datasets (laps, position, car_data, location). One call
    #    per driver_number; skip drivers that error out so a single failure
    #    doesn't abort ingestion. car_data/location are decimated per driver to
    #    ~TELEMETRY_SAMPLE_HZ and clipped to the race window to keep volume sane.
    race_start_dt = _parse_dt(sessions[0].get("date_start"))
    race_end_dt = _parse_dt(sessions[0].get("date_end"))

    laps = []
    position = []
    car_data = []
    location = []
    for d in drivers:
        driver_number = d.get("driver_number")
        if driver_number is None:
            continue
        driver_params = {"session_key": session_key, "driver_number": driver_number}
        try:
            laps.extend(_fetch("laps", driver_params))
        except (requests.exceptions.RequestException, ValueError):
            pass
        try:
            position.extend(_fetch("position", driver_params))
        except (requests.exceptions.RequestException, ValueError):
            pass

        raw_car_data = _fetch_optional("car_data", driver_params)
        car_data.extend(_reduce_telemetry(
            raw_car_data,
            keep_fields=["date", "driver_number", "speed"],
            start_dt=race_start_dt,
            end_dt=race_end_dt,
            min_interval_seconds=TELEMETRY_MIN_INTERVAL_SECONDS,
        ))

        raw_location = _fetch_optional("location", driver_params)
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
        return _json_response(500, {
            "error": "Saved to S3 but failed to fire EventBridge event",
            "details": str(e),
            "s3_key": s3_key,
        })

    return _json_response(200, {
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
    })
