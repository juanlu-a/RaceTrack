"""
Lambda triggered by EventBridge:
  Source: racetrack
  DetailType: SessionIngested
  Detail: { "bucket": "...", "key": "...", "session_key": "..." }

Reads the raw JSON bundle from S3, creates the RDS tables if they don't exist,
then upserts the session, drivers and laps rows into PostgreSQL. It also flattens
the time-series datasets (position, intervals, pit, race_control, laps,
starting_grid) into a unified, chronological `session_events` table.
"""
import json
import os

import boto3
import psycopg2
import psycopg2.extras

S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "racetrack")
DB_USER = os.environ.get("DB_USER", "racetrack")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "racetrack")

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    session_key        TEXT PRIMARY KEY,
    session_name       TEXT,
    session_type       TEXT,
    circuit_short_name TEXT,
    country_name       TEXT,
    location           TEXT,
    date_start         TEXT,
    date_end           TEXT,
    year               INTEGER,
    meeting_key        TEXT
);
"""

CREATE_DRIVERS = """
CREATE TABLE IF NOT EXISTS drivers (
    session_key  TEXT,
    driver_number INTEGER,
    full_name    TEXT,
    team_name    TEXT,
    country_code TEXT,
    PRIMARY KEY (session_key, driver_number)
);
"""

CREATE_LAPS = """
CREATE TABLE IF NOT EXISTS laps (
    session_key   TEXT,
    driver_number INTEGER,
    lap_number    INTEGER,
    lap_duration  FLOAT,
    i1_speed      INTEGER,
    i2_speed      INTEGER,
    st_speed      INTEGER,
    is_pit_out_lap BOOLEAN,
    PRIMARY KEY (session_key, driver_number, lap_number)
);
"""

# Unified, chronological event log used by downstream consumers (e.g. the
# simulation publisher). Each row is one event from one of the time-series
# datasets (position, intervals, pit, race_control, laps, starting_grid).
CREATE_SESSION_EVENTS = """
CREATE TABLE IF NOT EXISTS session_events (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    driver_id   INTEGER,
    payload     JSONB,
    "timestamp" TIMESTAMPTZ
);
"""

CREATE_SESSION_EVENTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_session_events_sid_ts
    ON session_events (session_id, "timestamp");
"""

DELETE_SESSION_EVENTS = "DELETE FROM session_events WHERE session_id = %s;"

INSERT_SESSION_EVENT = """
INSERT INTO session_events (session_id, event_type, driver_id, payload, "timestamp")
VALUES (%(session_id)s, %(event_type)s, %(driver_id)s, %(payload)s, %(timestamp)s);
"""

UPSERT_SESSION = """
INSERT INTO sessions (session_key, session_name, session_type, circuit_short_name,
                      country_name, location, date_start, date_end, year, meeting_key)
VALUES (%(session_key)s, %(session_name)s, %(session_type)s, %(circuit_short_name)s,
        %(country_name)s, %(location)s, %(date_start)s, %(date_end)s, %(year)s, %(meeting_key)s)
ON CONFLICT (session_key) DO UPDATE SET
    session_name       = EXCLUDED.session_name,
    session_type       = EXCLUDED.session_type,
    circuit_short_name = EXCLUDED.circuit_short_name,
    country_name       = EXCLUDED.country_name,
    location           = EXCLUDED.location,
    date_start         = EXCLUDED.date_start,
    date_end           = EXCLUDED.date_end,
    year               = EXCLUDED.year,
    meeting_key        = EXCLUDED.meeting_key;
"""

UPSERT_DRIVER = """
INSERT INTO drivers (session_key, driver_number, full_name, team_name, country_code)
VALUES (%(session_key)s, %(driver_number)s, %(full_name)s, %(team_name)s, %(country_code)s)
ON CONFLICT (session_key, driver_number) DO UPDATE SET
    full_name    = EXCLUDED.full_name,
    team_name    = EXCLUDED.team_name,
    country_code = EXCLUDED.country_code;
"""

UPSERT_LAP = """
INSERT INTO laps (session_key, driver_number, lap_number, lap_duration,
                  i1_speed, i2_speed, st_speed, is_pit_out_lap)
VALUES (%(session_key)s, %(driver_number)s, %(lap_number)s, %(lap_duration)s,
        %(i1_speed)s, %(i2_speed)s, %(st_speed)s, %(is_pit_out_lap)s)
ON CONFLICT (session_key, driver_number, lap_number) DO UPDATE SET
    lap_duration   = EXCLUDED.lap_duration,
    i1_speed       = EXCLUDED.i1_speed,
    i2_speed       = EXCLUDED.i2_speed,
    st_speed       = EXCLUDED.st_speed,
    is_pit_out_lap = EXCLUDED.is_pit_out_lap;
"""


def _s3_client():
    kwargs = {"region_name": AWS_REGION}
    if S3_ENDPOINT:
        # LocalStack mode: use dummy creds + custom endpoint
        kwargs.update({"aws_access_key_id": "test", "aws_secret_access_key": "test", "endpoint_url": S3_ENDPOINT})
    return boto3.client("s3", **kwargs)


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_events(session_key, session_data, payload):
    """Flatten the time-series datasets into a single chronological event list.

    Each dataset maps to one event_type. The OpenF1 `date` field is used as the
    event timestamp; laps use `date_start`; starting_grid has no timestamp so it
    falls back to the session start time.
    """
    session_start = session_data.get("date_start")

    # (dataset_key, event_type, timestamp_field, timestamp_fallback)
    mappings = [
        ("position", "position", "date", None),
        ("intervals", "interval", "date", None),
        ("pit", "pit", "date", None),
        ("race_control", "race_control", "date", None),
        ("laps", "lap", "date_start", None),
        ("starting_grid", "starting_grid", "date", session_start),
    ]

    events = []
    for dataset_key, event_type, ts_field, ts_fallback in mappings:
        for item in payload.get(dataset_key) or []:
            if not isinstance(item, dict):
                continue
            events.append({
                "session_id": session_key,
                "event_type": event_type,
                "driver_id": _int_or_none(item.get("driver_number")),
                "payload": psycopg2.extras.Json(item),
                "timestamp": item.get(ts_field) or ts_fallback,
            })
    return events


def handler(event, context):
    # EventBridge wraps the detail as a dict already
    detail = event.get("detail") or {}
    bucket = detail.get("bucket", "")
    key = detail.get("key", "")
    session_key = detail.get("session_key", "")

    if not bucket or not key or not session_key:
        return {"statusCode": 400, "body": json.dumps({
            "error": "Missing detail fields: bucket, key, session_key",
        })}

    # 1. Read raw JSON from S3
    try:
        s3 = _s3_client()
        obj = s3.get_object(Bucket=bucket, Key=key)
        payload = json.loads(obj["Body"].read())
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({
            "error": "Failed to read from S3", "details": str(e),
        })}

    session_data = payload.get("session") or {}
    drivers_data = payload.get("drivers") or []
    laps_data = payload.get("laps") or []

    # Flatten the time-series datasets into chronological events.
    events = _build_events(session_key, session_data, payload)

    # 2. Persist to RDS
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_SESSIONS)
                cur.execute(CREATE_DRIVERS)
                cur.execute(CREATE_LAPS)
                cur.execute(CREATE_SESSION_EVENTS)
                cur.execute(CREATE_SESSION_EVENTS_INDEX)

                # Upsert session
                cur.execute(UPSERT_SESSION, {
                    "session_key": str(session_data.get("session_key", session_key)),
                    "session_name": session_data.get("session_name"),
                    "session_type": session_data.get("session_type"),
                    "circuit_short_name": session_data.get("circuit_short_name"),
                    "country_name": session_data.get("country_name"),
                    "location": session_data.get("location"),
                    "date_start": str(session_data.get("date_start", "")),
                    "date_end": str(session_data.get("date_end", "")),
                    "year": session_data.get("year"),
                    "meeting_key": str(session_data.get("meeting_key", "")),
                })

                # Upsert drivers
                for d in drivers_data:
                    if not d.get("driver_number"):
                        continue
                    cur.execute(UPSERT_DRIVER, {
                        "session_key": session_key,
                        "driver_number": int(d["driver_number"]),
                        "full_name": d.get("full_name"),
                        "team_name": d.get("team_name"),
                        "country_code": d.get("country_code"),
                    })

                # Upsert laps
                for lap in laps_data:
                    if lap.get("driver_number") is None or lap.get("lap_number") is None:
                        continue
                    cur.execute(UPSERT_LAP, {
                        "session_key": session_key,
                        "driver_number": int(lap["driver_number"]),
                        "lap_number": int(lap["lap_number"]),
                        "lap_duration": lap.get("lap_duration"),
                        "i1_speed": lap.get("i1_speed"),
                        "i2_speed": lap.get("i2_speed"),
                        "st_speed": lap.get("st_speed"),
                        "is_pit_out_lap": bool(lap.get("is_pit_out_lap", False)),
                    })

                # Rebuild session_events for this session (idempotent re-ingest)
                cur.execute(DELETE_SESSION_EVENTS, (session_key,))
                for ev in events:
                    cur.execute(INSERT_SESSION_EVENT, ev)

        conn.close()
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({
            "error": "Failed to write to RDS", "details": str(e),
        })}

    return {"statusCode": 200, "body": json.dumps({
        "message": "Session saved to RDS successfully",
        "session_key": session_key,
        "drivers_saved": len(drivers_data),
        "laps_saved": len(laps_data),
        "events_saved": len(events),
    })}
