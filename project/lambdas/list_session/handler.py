"""
Lambda for API Gateway (HTTP API):
  GET /sessions[?year=...]  → Returns sessions from RDS (previously ingested via ingest_session)
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


def _extract_method(event: dict) -> str:
    return (event.get("requestContext", {}).get("http", {}).get("method") or "").upper()


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
    )


def handler(event, context):
    method = _extract_method(event)
    if method and method != "GET":
        return _json_response(405, {"error": "Method not allowed. Use GET"})

    params = event.get("queryStringParameters") or {}
    year = (params.get("year") or "").strip()
    if year and not year.isdigit():
        return _json_response(400, {
            "error": "Invalid query parameter: year must be numeric",
            "example": "?year=2023",
        })

    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if year:
                cur.execute(
                    "SELECT * FROM sessions WHERE year = %s ORDER BY date_start", (int(year),)
                )
            else:
                cur.execute("SELECT * FROM sessions ORDER BY date_start")
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return _json_response(500, {"error": "Failed to query RDS", "details": str(e)})

    sessions = [dict(r) for r in rows]

    if year and not sessions:
        return _json_response(404, {"error": f"No sessions found for year '{year}'"})

    return _json_response(200, {
        "count": len(sessions),
        "year": int(year) if year else None,
        "sessions": sessions,
    })
