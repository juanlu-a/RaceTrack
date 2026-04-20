"""
Lambda for API Gateway (HTTP API):
  GET /driver-laps?session_key=...&driver_number=...

Returns the list of laps for a driver in a session, ordered by lap number.
Data is read from the laps table in RDS (populated by save_session).

Each lap includes: lap_number, lap_duration, i1_speed, i2_speed, st_speed,
is_pit_out_lap.
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
            cur.execute(
                """
                SELECT lap_number, lap_duration, i1_speed, i2_speed, st_speed, is_pit_out_lap
                FROM laps
                WHERE session_key = %s AND driver_number = %s
                ORDER BY lap_number
                """,
                (session_key, driver_number_int),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return _json_response(500, {"error": "Failed to query RDS", "details": str(e)})

    if not rows:
        return _json_response(404, {
            "error": f"No laps found for driver {driver_number} in session '{session_key}'",
            "hint": f"Run GET /ingest?session_key={session_key} first",
        })

    laps = [
        {
            "lapNumber": r["lap_number"],
            "lapDuration": float(r["lap_duration"]) if r["lap_duration"] is not None else None,
            "i1Speed": r["i1_speed"],
            "i2Speed": r["i2_speed"],
            "stSpeed": r["st_speed"],
            "isPitOutLap": r["is_pit_out_lap"],
        }
        for r in rows
    ]

    return _json_response(200, {
        "sessionKey": session_key,
        "driverNumber": driver_number_int,
        "lapCount": len(laps),
        "laps": laps,
    })
