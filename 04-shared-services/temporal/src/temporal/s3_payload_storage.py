from __future__ import annotations

import asyncio
import uuid
from typing import Any

import aioboto3
from aiobotocore.config import AioConfig
from aiobotocore.session import ClientCreatorContext
from botocore.exceptions import ClientError
from event_logging import EventLogger, LoggingSettings
from event_logging.enums import EventAction, EventCategory, EventOutcome
from event_logging.settings import Environment
from types_aiobotocore_s3.client import S3Client

PAYLOAD_PATH_PREFIX = "payloads"


class S3PayloadStorage:
    bucket_name: str
    endpoint_url: str
    session: aioboto3.Session
    _bucket_exists: bool
    _client: S3Client | None = None
    _client_cm: ClientCreatorContext[S3Client] | None = None
    _client_lock: asyncio.Lock
    logger: EventLogger

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self._bucket_exists = False
        self._client_lock = asyncio.Lock()
        self.session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        env = (
            Environment.DEVELOPMENT
            if "localhost" in endpoint_url
            else Environment.PRODUCTION
        )
        self.logger = EventLogger(
            service_name="temporal",
            settings=LoggingSettings(ENV=env),
        )

    async def _get_client(self) -> S3Client:
        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is not None:
                return self._client

            config = AioConfig(
                signature_version="s3v4",
                request_checksum_calculation="WHEN_REQUIRED",
                response_checksum_validation="WHEN_REQUIRED",
            )
            self._client_cm = self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                config=config,
            )
            self._client = await self._client_cm.__aenter__()
            return self._client

    async def _ensure_bucket(self, s3: Any) -> None:
        if self._bucket_exists:
            return
        try:
            await s3.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                await s3.create_bucket(Bucket=self.bucket_name)
            else:
                raise
        self._bucket_exists = True

    async def put(self, payload_data: bytes) -> str:
        log_base: dict[str, Any] = {
            "category": EventCategory.FILE,
            "action": EventAction.UPLOAD,
        }
        key: str = f"{PAYLOAD_PATH_PREFIX}/{uuid.uuid4()}"
        try:
            s3 = await self._get_client()
            await self._ensure_bucket(s3)
            await s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=payload_data,
                ContentType="application/octet-stream",
            )

            self.logger.info(
                **log_base,
                outcome=EventOutcome.SUCCESS,
                message=f"Uploaded key={key} size={len(payload_data)}",
            )
            return key
        except Exception as e:
            self.logger.error(
                **log_base,
                outcome=EventOutcome.FAILURE,
                message=f"Failed upload key={key}: {e}",
            )
            raise

    async def get(self, key: str) -> bytes:
        log_base: dict[str, Any] = {
            "category": EventCategory.FILE,
            "action": EventAction.DOWNLOAD,
        }
        try:
            s3 = await self._get_client()
            response = await s3.get_object(Bucket=self.bucket_name, Key=key)
            data = await response["Body"].read()
            self.logger.info(
                **log_base,
                outcome=EventOutcome.SUCCESS,
                message=f"Downloaded key={key} size={len(data)}",
            )
            return data
        except Exception as e:
            self.logger.error(
                **log_base,
                outcome=EventOutcome.FAILURE,
                message=f"Failed download key={key}: {e}",
            )
            raise

    async def close(self) -> None:
        if self._client_cm is None:
            return
        await self._client_cm.__aexit__(None, None, None)
        self._client = None
        self._client_cm = None
        self._bucket_exists = False
