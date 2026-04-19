"""
Lambda for API Gateway (HTTP API):
  GET /driver-summary?session_key=...&driver_number=...

Returns lap statistics for a driver in a session, computed from the
laps table in RDS (populated by save_session after ingestion):
  - total_laps
  - best_lap_duration  (fastest lap, excluding null values)
  - avg_lap_duration   (average of valid laps excluding pit-out laps)
  - top_speed          (max speed trap reading)
  - avg_speed          (average speed trap reading)
"""
import json
import os

import psycopg2
import psycopg2.extras

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "racetrack")
DB_USER = os.environ.get("DB_USER", "racetrack")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "racetrack")

STATS_QUERY = """
SELECT
    COUNT(*)                                        AS total_laps,
    MIN(lap_duration)                               AS best_lap_duration,
    AVG(lap_duration) FILTER (WHERE is_pit_out_lap = FALSE AND lap_duration IS NOT NULL)
                                                    AS avg_lap_duration,
    MAX(st_speed)                                   AS top_speed,
    AVG(st_speed) FILTER (WHERE st_speed IS NOT NULL)
                                                    AS avg_speed
FROM laps
WHERE session_key = %s
  AND driver_number = %s;
"""

DRIVER_QUERY = """
SELECT full_name, team_name, country_code
FROM drivers
WHERE session_key = %s AND driver_number = %s
LIMIT 1;
"""


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


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    session_key = (params.get("session_key") or "").strip()
    driver_number = (params.get("driver_number") or "").strip()

    if not session_key:
        return _json_response(400, {
            "error": "Missing query parameter: session_key",
            "example": "?session_key=9158&driver_number=1",
        })
    if not driver_number or not driver_number.isdigit():
        return _json_response(400, {
            "error": "Missing or invalid query parameter: driver_number (must be numeric)",
            "example": "?session_key=9158&driver_number=1",
        })

    driver_number_int = int(driver_number)

    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(DRIVER_QUERY, (session_key, driver_number_int))
            driver_row = cur.fetchone()

            cur.execute(STATS_QUERY, (session_key, driver_number_int))
            stats_row = cur.fetchone()
        conn.close()
    except Exception as e:
        return _json_response(500, {"error": "Failed to query RDS", "details": str(e)})

    if not driver_row:
        return _json_response(404, {
            "error": f"No driver {driver_number} found for session_key '{session_key}'",
            "hint": f"Run GET /ingest?session_key={session_key} first",
        })

    def _round(value, digits=3):
        return round(float(value), digits) if value is not None else None

    return _json_response(200, {
        "sessionKey": session_key,
        "driverNumber": driver_number_int,
        "driverName": driver_row["full_name"],
        "team": driver_row["team_name"],
        "country": driver_row["country_code"],
        "stats": {
            "totalLaps": int(stats_row["total_laps"]) if stats_row["total_laps"] else 0,
            "bestLapDuration": _round(stats_row["best_lap_duration"]),
            "avgLapDuration": _round(stats_row["avg_lap_duration"]),
            "topSpeed": int(stats_row["top_speed"]) if stats_row["top_speed"] else None,
            "avgSpeed": _round(stats_row["avg_speed"], 1),
        },
    })
