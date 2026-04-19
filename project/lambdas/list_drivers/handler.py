"""
Lambda for API Gateway (HTTP API):
  GET /drivers?session_key=...  → Returns drivers for a session from RDS
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
    if not session_key:
        return _json_response(400, {
            "error": "Missing query parameter: session_key",
            "example": "?session_key=9158",
        })

    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM drivers WHERE session_key = %s ORDER BY driver_number",
                (session_key,),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return _json_response(500, {"error": "Failed to query RDS", "details": str(e)})

    if not rows:
        return _json_response(404, {
            "error": f"No drivers found for session_key '{session_key}'",
            "hint": f"Run GET /ingest?session_key={session_key} first",
        })

    pilots = [
        {
            "pilotName": r["full_name"],
            "pilotNumber": r["driver_number"],
            "pilotTeam": r["team_name"],
            "pilotCountry": r["country_code"],
        }
        for r in rows
    ]

    return _json_response(200, {
        "sessionKey": session_key,
        "pilotCount": len(pilots),
        "pilots": pilots,
    })
