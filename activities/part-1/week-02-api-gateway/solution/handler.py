"""
Week 2: API Gateway — Session Handlers

TODO: Implement three API endpoints:
1. GET /sessions — List 2024 race sessions from OpenF1
2. GET /sessions/{session_key} — Get a specific session from OpenF1
3. POST /sessions/{session_key}/ingest — Fetch session + driver data from OpenF1

Hints:
- Path parameters: event["pathParameters"]["session_key"]
- Query parameters: event.get("queryStringParameters") or {}
- Request body: json.loads(event["body"])
- Always include Content-Type header in response
- Catch requests.RequestException for API errors
"""
import json
import logging
import os

import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

OPENF1_BASE_URL = os.getenv("OPENF1_BASE_URL", "https://api.openf1.org")
HEADERS = {"Content-Type": "application/json"}


def list_sessions(event, context):
    """GET /sessions — Return list of 2024 race sessions from OpenF1."""
    try:
        response = requests.get(
            f"{OPENF1_BASE_URL}/v1/sessions",
            params={"session_type": "Race", "year": 2024},
            timeout=10,
        )
        response.raise_for_status()

        sessions = response.json()
        simplified_sessions = [
            {
                "session_key": session.get("session_key"),
                "session_name": session.get("session_name"),
                "session_type": session.get("session_type"),
                "circuit_short_name": session.get("circuit_short_name"),
                "date_start": session.get("date_start"),
            }
            for session in sessions
        ]

        return {
            "statusCode": 200,
            "body": json.dumps({"sessions": simplified_sessions}),
            "headers": HEADERS,
        }
    except requests.RequestException:
        logger.exception("Failed to fetch sessions from OpenF1")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to fetch sessions"}),
            "headers": HEADERS,
        }


def get_session(event, context):
    """GET /sessions/{session_key} — Get session details from OpenF1."""
    path_parameters = event.get("pathParameters") or {}
    session_key = path_parameters.get("session_key")

    if not session_key:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing session_key path parameter"}),
            "headers": HEADERS,
        }

    try:
        response = requests.get(
            f"{OPENF1_BASE_URL}/v1/sessions",
            params={"session_key": session_key},
            timeout=10,
        )
        response.raise_for_status()

        sessions = response.json()
        if not sessions:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Session not found"}),
                "headers": HEADERS,
            }

        return {
            "statusCode": 200,
            "body": json.dumps({"session": sessions[0]}),
            "headers": HEADERS,
        }
    except requests.RequestException:
        logger.exception("Failed to fetch session from OpenF1")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to fetch session"}),
            "headers": HEADERS,
        }


def ingest_session(event, context):
    """POST /sessions/{session_key}/ingest — Fetch session and driver data."""
    path_parameters = event.get("pathParameters") or {}
    session_key = path_parameters.get("session_key")

    if not session_key:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing session_key path parameter"}),
            "headers": HEADERS,
        }

    try:
        session_response = requests.get(
            f"{OPENF1_BASE_URL}/v1/sessions",
            params={"session_key": session_key},
            timeout=10,
        )
        session_response.raise_for_status()
        sessions = session_response.json()

        if not sessions:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Session not found"}),
                "headers": HEADERS,
            }

        session = sessions[0]

        drivers_response = requests.get(
            f"{OPENF1_BASE_URL}/v1/drivers",
            params={"session_key": session_key},
            timeout=10,
        )
        drivers_response.raise_for_status()
        drivers = drivers_response.json()

        drivers_summary = [
            {
                "driver_number": driver.get("driver_number"),
                "name_acronym": driver.get("name_acronym"),
            }
            for driver in drivers
        ]

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "session_key": session.get("session_key"),
                    "session_name": session.get("session_name"),
                    "drivers_found": len(drivers_summary),
                    "drivers": drivers_summary,
                }
            ),
            "headers": HEADERS,
        }
    except requests.RequestException:
        logger.exception("Failed to ingest session from OpenF1")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to ingest session"}),
            "headers": HEADERS,
        }
