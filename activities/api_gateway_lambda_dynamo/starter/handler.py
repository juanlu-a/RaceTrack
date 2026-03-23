"""
Lambda detrás de API Gateway (HTTP API): consulta pilotos OpenF1 por session_key.
Si ya hay una fila en DynamoDB para esa sesión, responde desde caché; si no, llama a OpenF1 y guarda.
GET /cache expone lectura de la tabla de caché (scan o un ítem por session_key).
"""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
import requests

# Variables de entorno (Lambda: template.yaml > Environment > Variables;
# SAM local: env.json con la clave = ID lógico de la función, p. ej. F1DriversApiFunction)
# DYNAMODB_ENDPOINT_URL (opcional): p. ej. http://host.docker.internal:8000 para DynamoDB Local + sam local
TABLE_NAME = os.environ.get("TABLE_NAME")


def _dynamodb_resource():
    endpoint = (os.environ.get("DYNAMODB_ENDPOINT_URL") or "").strip()
    if endpoint:
        region = (
            os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_REGION")
            or "us-east-1"
        )
        return boto3.resource("dynamodb", endpoint_url=endpoint, region_name=region)
    return boto3.resource("dynamodb")


def _json_response(
    status_code: int,
    body: Dict[str, Any],
    extra_headers: Optional[Dict[str, str]] = None,
) -> dict:
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, default=str),
    }


def _json_safe(value: Any) -> Any:
    """Decimales y estructuras Dynamo → tipos serializables en JSON."""
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _for_dynamodb(value):
    """DynamoDB no acepta float; OpenF1 puede devolver números como float en JSON."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_for_dynamodb(v) for v in value]
    if isinstance(value, dict):
        return {k: _for_dynamodb(v) for k, v in value.items()}
    return value


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


def _handle_cache(event) -> dict:
    """GET /cache — scan de la tabla o GET /cache?session_key=… para un ítem."""
    params = event.get("queryStringParameters") or {}
    session_key = (params.get("session_key") or "").strip()
    table = _dynamodb_resource().Table(TABLE_NAME)

    if session_key:
        try:
            resp = table.get_item(Key={"session_key": session_key})
        except Exception as e:
            return _json_response(500, {"error": "Error leyendo DynamoDB", "details": str(e)})
        if "Item" not in resp:
            return _json_response(
                404,
                {"error": "No hay caché para ese session_key", "sessionKey": session_key},
            )
        return _json_response(200, {"item": _json_safe(resp["Item"])})

    limit_raw = (params.get("limit") or "50").strip()
    try:
        limit = min(max(int(limit_raw), 1), 500)
    except ValueError:
        limit = 50

    try:
        resp = table.scan(Limit=limit)
    except Exception as e:
        return _json_response(500, {"error": "Error escaneando DynamoDB", "details": str(e)})

    items = [_json_safe(i) for i in resp.get("Items", [])]
    out: Dict[str, Any] = {
        "tableName": TABLE_NAME,
        "count": len(items),
        "items": items,
    }
    if resp.get("LastEvaluatedKey"):
        out["lastEvaluatedKey"] = _json_safe(resp["LastEvaluatedKey"])
    return _json_response(200, out)


def _handle_drivers(event) -> dict:
    """GET /drivers?session_key=…"""
    params = event.get("queryStringParameters") or {}
    session_key = (params.get("session_key") or "").strip()
    if not session_key:
        return _json_response(
            400,
            {"error": "Falta el query parameter session_key", "ejemplo": "?session_key=9159"},
        )

    endpoint_hint = (os.environ.get("DYNAMODB_ENDPOINT_URL") or "").strip()
    table = _dynamodb_resource().Table(TABLE_NAME)

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
    item = _for_dynamodb({
        "session_key": session_key,
        "pilots": pilots,
        "pilot_count": len(pilots),
        "cached_at": now,
    })

    try:
        table.put_item(Item=item)
    except Exception as e:
        return _json_response(500, {"error": "Error escribiendo en DynamoDB", "details": str(e)})

    dbg = {}
    if endpoint_hint:
        dbg["X-Dynamo-Endpoint"] = endpoint_hint

    return _json_response(
        200,
        {
            "source": "openf1",
            "sessionKey": session_key,
            "pilots": pilots,
            "pilotCount": len(pilots),
            "cachedAt": now,
        },
        extra_headers=dbg,
    )


def handler(event, context):
    if not TABLE_NAME:
        return _json_response(500, {"error": "TABLE_NAME is not configured"})

    endpoint_hint = (os.environ.get("DYNAMODB_ENDPOINT_URL") or "").strip()
    print(
        f"[handler] TABLE_NAME={TABLE_NAME!r} DYNAMODB_ENDPOINT_URL={endpoint_hint!r}",
        flush=True,
    )

    raw = (event.get("rawPath") or "").rstrip("/") or "/"
    if raw == "/cache":
        return _handle_cache(event)
    if raw == "/drivers":
        return _handle_drivers(event)

    return _json_response(404, {"error": "Ruta no encontrada", "path": raw})
