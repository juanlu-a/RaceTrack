"""
Repositorio de estadísticas de pilotos por sesión (tabla f1_driver_stats).
PK: session_key, SK: driver_number.
"""
import os
from typing import Any, Dict, Optional

import boto3


class DriverStatsRepository:
    def __init__(self) -> None:
        kwargs = {"region_name": os.getenv("AWS_REGION", "us-east-1")}
        endpoint = os.getenv("AWS_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        self.dynamodb = boto3.resource("dynamodb", **kwargs)
        self.table = self.dynamodb.Table(
            os.getenv("DRIVER_STATS_TABLE", "f1_driver_stats")
        )

    def save(self, item: dict) -> None:
        """Guarda un registro de piloto en una sesión."""
        self.table.put_item(Item=item)

    def get(self, session_key: int, driver_number: int) -> dict:
        """Obtiene el registro para una sesión y número de piloto."""
        resp = self.table.get_item(
            Key={"session_key": session_key, "driver_number": driver_number}
        )
        record = resp.get("Item")
        if record is None:
            raise KeyError(
                f"No driver stats for session_key={session_key!r}, "
                f"driver_number={driver_number!r}"
            )
        return record

    def list_by_session(self, session_key: int) -> list:
        """Todos los pilotos de una sesión (query por partition key)."""
        resp = self.table.query(
            KeyConditionExpression="session_key = :sk",
            ExpressionAttributeValues={":sk": session_key},
        )
        return resp.get("Items", [])

    def delete(
        self, session_key: int, driver_number: int
    ) -> Optional[Dict[str, Any]]:
        """Elimina un registro; devuelve los atributos previos si existía."""
        resp = self.table.delete_item(
            Key={"session_key": session_key, "driver_number": driver_number},
            ReturnValues="ALL_OLD",
        )
        return resp.get("Attributes")
