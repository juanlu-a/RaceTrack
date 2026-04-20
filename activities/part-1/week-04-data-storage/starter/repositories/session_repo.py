"""
Repositorio de sesiones F1 en DynamoDB (tabla f1_sessions).
"""
import os

import boto3


class SessionRepository:
    def __init__(self) -> None:
        kwargs = {"region_name": os.getenv("AWS_REGION", "us-east-1")}
        endpoint = os.getenv("AWS_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        self.dynamodb = boto3.resource("dynamodb", **kwargs)
        self.table = self.dynamodb.Table(os.getenv("SESSIONS_TABLE", "f1_sessions"))

    def save(self, session: dict) -> None:
        """Guarda una sesión (put_item)."""
        self.table.put_item(Item=session)

    def get(self, session_key: int) -> dict:
        """Obtiene una sesión por session_key."""
        resp = self.table.get_item(Key={"session_key": session_key})
        item = resp.get("Item")
        if item is None:
            raise KeyError(f"No session for session_key={session_key!r}")
        return item

    def list_all(self) -> list:
        """Lista todas las sesiones (scan)."""
        resp = self.table.scan()
        return resp.get("Items", [])
