"""
Lambda detrás de API Gateway (HTTP API): consulta pilotos OpenF1 por session_key.
Si ya hay una fila en DynamoDB para esa sesión, responde desde caché; si no, llama a OpenF1 y guarda.
"""
import json
import os
from datetime import datetime, timezone

import boto3
import requests

_endpoint = os.environ.get("DYNAMODB_ENDPOINT")
if _endpoint:
    # Local dev: hardcode dummy credentials so DynamoDB Local doesn't reject the
    # expired/real SSO token that SAM injects into the container env vars.
    dynamodb = boto3.resource(
        "dynamodb",
        endpoint_url=_endpoint,
        aws_access_key_id="DUMMYIDEXAMPLE",
        aws_secret_access_key="dummysecretkey",
        aws_session_token=None,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-2"),
    )
else:
    dynamodb = boto3.resource("dynamodb")

# Variables de entorno (Lambda: template.yaml > Environment > Variables;
# SAM local: env.json con la clave = ID lógico de la función, p. ej. F1DriversApiFunction)
TABLE_NAME = os.environ.get("TABLE_NAME")


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _normalize_drivers(raw: list) -> list:
    pilots = []
    for driver in raw:
        pilots.append({
            "pilotName": driver.get("full_name"),
            "pilotNumber": driver.get("driver_number"),
            "pilotTeam": driver.get("team_name"),
            "pilotCountry": driver.get("country_code"),
        })
    return pilots


def handler(event, context):
    if not TABLE_NAME:
        return _json_response(500, {"error": "TABLE_NAME is not configured"})

    params = event.get("queryStringParameters") or {}
    session_key = (params.get("session_key") or "").strip()
    if not session_key:
        return _json_response(
            400,
            {"error": "Falta el query parameter session_key", "ejemplo": "?session_key=9159"},
        )

    table = dynamodb.Table(TABLE_NAME)

    try:
        resp = table.get_item(Key={"session_key": session_key})
    except Exception as e:
        return _json_response(500, {"error": "Error leyendo DynamoDB", "details": str(e)})

    if "Item" in resp:
        item = resp["Item"]
        return _json_response(200, {
            "source": "dynamodb",
            "sessionKey": session_key,
            "pilots": item.get("pilots", []),
            "pilotCount": int(item.get("pilot_count", 0)),
            "cachedAt": item.get("cached_at"),
        })

    url = f"https://api.openf1.org/v1/drivers?session_key={session_key}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        return _json_response(502, {"error": "Fallo al llamar a OpenF1", "details": str(e)})

    if not isinstance(data, list):
        return _json_response(502, {"error": "Respuesta OpenF1 inesperada"})

    pilots = _normalize_drivers(data)
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "session_key": session_key,
        "pilots": pilots,
        "pilot_count": len(pilots),
        "cached_at": now,
    }

    try:
        table.put_item(Item=item)
    except Exception as e:
        return _json_response(500, {"error": "Error escribiendo en DynamoDB", "details": str(e)})

    return _json_response(200, {
        "source": "openf1",
        "sessionKey": session_key,
        "pilots": pilots,
        "pilotCount": len(pilots),
        "cachedAt": now,
    })
