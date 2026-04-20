"""
Almacenamiento de respuestas crudas de la API en S3.
"""
import os
from typing import Optional

import boto3


class RawDataRepository:
    def __init__(self) -> None:
        kwargs = {"region_name": os.getenv("AWS_REGION", "us-east-1")}
        endpoint = os.getenv("AWS_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        self.client = boto3.client("s3", **kwargs)
        self.bucket = os.getenv("RAW_DATA_BUCKET", "f1-raw-data")

    def put(self, key: str, body: bytes, content_type: Optional[str] = None) -> None:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body, **extra)

    def get(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
