from collections.abc import AsyncGenerator
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, BinaryIO

import aioboto3
from aioboto3.session import Session
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError
from event_logging.enums import EventAction, EventCategory, EventOutcome

from src.config.settings import settings
from src.services.storage_provider.storage_provider_base_service import (
    BaseStorageProviderService,
)
from src.utils.logger import logger


class AsyncS3StorageClient(BaseStorageProviderService):
    """Async S3 storage client for MinIO and Ceph RGW.

    Implements non-blocking operations using aioboto3.
    Inherits common path handling from BaseStorageProviderService.
    """

    def __init__(
        self,
        bucket_name: str = settings.BUCKET_NAME,
        doc_store_path: str = settings.DOC_STORE_PATH,
        endpoint_url: str = settings.S3_ENDPOINT_URL,  # type: ignore
        public_endpoint: str | None = settings.S3_EXTERNAL_URL,
        access_key: str = settings.S3_ACCESS_KEY_ID,  # type: ignore
        secret_key: str = settings.S3_SECRET_ACCESS_KEY,  # type: ignore
        region: str = settings.S3_REGION,  # type: ignore
        **_,
    ):
        super().__init__(
            bucket_name=bucket_name,
            doc_store_path=doc_store_path,
        )
        self.endpoint_url = endpoint_url
        self.public_endpoint = public_endpoint or endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

        self.session = aioboto3.Session()
        self.config = AioConfig(
            signature_version="s3v4",
            region_name=region,
            retries={"max_attempts": 3},
            request_checksum_calculation="WHEN_REQUIRED",
            response_checksum_validation="WHEN_REQUIRED",
        )
        self.private_kwargs = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "endpoint_url": endpoint_url,
            "config": self.config,
        }
        self.public_kwargs = self.private_kwargs.copy()
        self.public_kwargs["endpoint_url"] = self.public_endpoint

        logger.debug(
            action=EventAction.NOTIFY,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.FILE,
            message=(
                f"AsyncS3Client initialized: bucket={bucket_name}, "
                f"endpoint={endpoint_url}"
            ),
        )

        self._public_client: Session = None
        self._private_client: Session = None

    def _get_key(self, document_name: str) -> str:
        """Convert document name to S3 object key."""
        return f"{self.doc_store_path}/{document_name}".lstrip("/")

    async def _ensure_clients(self):
        """Ensures clients exist."""
        if self._private_client is None or self._public_client is None:
            await self.initialize()

    async def _get_head_object(self, document_name: str) -> dict[str, Any]:
        """Helper method to get object head.

        Raises:
            FileNotFoundError: If key does not exist.
            ClientError: If failed to get head.
        """
        key = self._get_key(document_name)
        try:
            head = await self._private_client.head_object(
                Bucket=self.bucket_name,
                Key=key,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(f"Document '{document_name}' not found") from e
            raise

        return head

    async def initialize(self):
        """Enter async context for long-lived clients (call once at startup)."""
        self._private_client = await self.session.client(
            service_name="s3",
            **self.private_kwargs,
        ).__aenter__()
        self._public_client = await self.session.client(
            service_name="s3",
            **self.public_kwargs,
        ).__aenter__()
        logger.info(
            action=EventAction.NOTIFY,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.FILE,
            message="Long-lived S3 clients initialized",
        )

    async def close(self):
        """Exit async contexts (call once on shutdown)."""
        if self._private_client:
            await self._private_client.__aexit__(None, None, None)
            self._private_client = None
        if self._public_client:
            await self._public_client.__aexit__(None, None, None)
            self._public_client = None
        logger.info(
            action=EventAction.NOTIFY,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.FILE,
            message="S3 clients closed",
        )

    async def bucket_exists(self) -> bool:
        """Check if the configured bucket exists in S3 storage.

        Returns:
            True if the bucket exists, False otherwise.

        Raises:
            ClientError: On unexpected S3 errors (logged but not raised).
        """
        await self._ensure_clients()
        try:
            await self._private_client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.debug(
                    action=EventAction.READ,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    message=f"Bucket '{self.bucket_name}' does not exist",
                )
                return False
            else:
                logger.warn(
                    action=EventAction.READ,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    message=f"Error checking bucket '{self.bucket_name}': {str(e)}",
                )
                return False

    async def document_exists(self, document_name: str) -> bool:
        """Check if a document exists in storage.

        Args:
            document_name: Name of the document (relative to doc_store_path).

        Returns:
            True if the document exists, False otherwise.

        Raises:
            ClientError: If the HEAD request fails for reasons other than 404.
        """
        await self._ensure_clients()
        try:
            await self._get_head_object(document_name)
            return True
        except FileNotFoundError:
            return False

    async def get_file_mime_type(self, document_name: str) -> str:
        """Retrieve the MIME type (Content-Type) of a stored document.

        Args:
            document_name: Name of the document.

        Returns:
            The Content-Type header value, or None if not set.

        Raises:
            FileNotFoundError: If the object does not exist.
            ClientError: If the HEAD request fails for reasons other than 404.
            ValueError: If the MIME type is not set.
        """
        await self._ensure_clients()

        head = await self._get_head_object(document_name)

        content_type = head.get("ContentType") or head.get("content_type")

        if not content_type:
            raise ValueError(f"Object '{document_name}' does not have a MIME type set")

        return content_type

    async def delete_document(self, document_name: str) -> None:
        """Delete a document from storage.

        Args:
            document_name: Name of the document to delete.

        Raises:
            FileNotFoundError: If the document does not exist.
            ClientError: On other S3 errors.
        """
        await self._ensure_clients()
        key = self._get_key(document_name)
        if await self.document_exists(document_name):
            await self._private_client.delete_object(
                Bucket=self.bucket_name,
                Key=key,
            )
        else:
            raise FileNotFoundError(f"Document '{document_name}' not found")

    async def copy_document(
        self,
        source_name: str,
        destination_name: str,
        overwrite: bool = False,
    ) -> None:
        """Copy a document to a new name within the same bucket.

        Args:
            source_name: Original document name.
            destination_name: New document name.
            overwrite: If False, raise FileExistsError if destination exists.

        Raises:
            FileNotFoundError: If source does not exist.
            FileExistsError: If destination exists and overwrite=False.
            ClientError: On copy failure.
        """
        await self._ensure_clients()
        src_key = self._get_key(source_name)
        dst_key = self._get_key(destination_name)
        if not overwrite and await self.document_exists(destination_name):
            raise FileExistsError(f"Destination '{destination_name}' exists")
        if not await self.document_exists(source_name):
            raise FileNotFoundError(f"Source '{source_name}' not found")
        await self._private_client.copy_object(
            Bucket=self.bucket_name,
            Key=dst_key,
            CopySource=f"{self.bucket_name}/{src_key}",
        )

    async def upload_document_from_obj(
        self,
        document_name: str,
        file_obj: BinaryIO,
        overwrite: bool = False,
        mime_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Upload a file-like object to storage.

        Args:
            document_name: Destination document name.
            file_obj: Binary file-like object (must be seekable).
            overwrite: If False, raise FileExistsError if file exists.
            mime_type: Optional Content-Type to set.
            metadata: Optional user metadata to store with the object
                  (keys and values must be strings).

        Raises:
            FileExistsError: If file exists and overwrite=False.
            ClientError: On upload failure.
        """
        await self._ensure_clients()
        key = self._get_key(document_name)

        extra_args: dict[str, str | dict[str, str]] = {}
        if mime_type:
            extra_args["ContentType"] = mime_type
        if metadata:
            extra_args["Metadata"] = metadata

        if not overwrite and await self.document_exists(document_name):
            raise FileExistsError(f"Document '{document_name}' exists")

        file_obj.seek(0)
        await self._private_client.upload_fileobj(
            Fileobj=file_obj,
            Bucket=self.bucket_name,
            Key=key,
            ExtraArgs=extra_args,
        )

    async def download_document_as_file_obj(self, document_name: str) -> BytesIO:
        """Download a document into a BytesIO object.

        Args:
            document_name: Name of the document to download.

        Returns:
            BytesIO containing the document content.

        Raises:
            FileNotFoundError: If the document does not exist.
            ClientError: On download failure.
        """
        await self._ensure_clients()
        key = self._get_key(document_name)
        if not await self.document_exists(document_name):
            raise FileNotFoundError(f"Document '{document_name}' not found")
        bio = BytesIO()
        await self._private_client.download_fileobj(
            Bucket=self.bucket_name,
            Key=key,
            Fileobj=bio,
        )
        bio.seek(0)
        return bio

    async def download_document_stream(  # type: ignore
        self,
        document_name: str,
        chunk_size: int = 256 * 1024,
    ) -> AsyncGenerator[bytes]:
        """
        Yield document content as byte chunks. Raises FileNotFoundError.

        Args:
            document_name (str): Document name in storage.
            chunk_size (int): Size of the individual chunks.

        Returns:
            AsyncGenerator[bytes]: Async iterator over the file content.

        Raises:
            FileNotFoundError: If the document does not exist.
        """
        await self._ensure_clients()
        key = self._get_key(document_name)
        try:
            response = await self._private_client.get_object(
                Bucket=self.bucket_name,
                Key=key,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError(f"Document '{document_name}' not found") from e
            raise

        body = response["Body"]
        try:
            while True:
                chunk = await body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()

    async def list_all_documents(
        self, path: bool = False, prefix: str | None = None
    ) -> list[str]:
        """List all documents under the configured path.

        Args:
            path: If True, return relative paths; else return filenames only.
            prefix: Optional prefix filter (relative to doc_store_path).

        Returns:
            List of document names or paths.
        """
        await self._ensure_clients()
        paginator = self._private_client.get_paginator("list_objects_v2")
        list_kwargs = {
            "Bucket": self.bucket_name,
            "Prefix": self._get_key(prefix or ""),
        }
        files = []
        async for page in paginator.paginate(**list_kwargs):
            for obj in page.get("Contents", []):
                name = (
                    PurePosixPath(obj["Key"])
                    .relative_to(self.doc_store_path.rstrip("/") + "/")
                    .as_posix()
                )
                if path:
                    files.append(name)
                else:
                    files.append(PurePosixPath(name).name)
        return files

    async def generate_upload_signed_url(
        self,
        document_name: str,
        expiration_minutes: int = 15,
        mime_type: str | None = None,
    ) -> str:
        """Generate a presigned URL for direct upload.

        Args:
            document_name: Name of the document to upload.
            expiration_minutes: URL validity duration in minutes.
            mime_type: Optional Content-Type restriction.

        Returns:
            Presigned PUT URL.

        Raises:
            FileExistsError: If document already exists.
        """
        await self._ensure_clients()
        if await self.document_exists(document_name):
            raise FileExistsError(f"Document '{document_name}' exists")
        key = self._get_key(document_name)
        params = {"Bucket": self.bucket_name, "Key": key}
        if mime_type:
            params["ContentType"] = mime_type
        url = await self._public_client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expiration_minutes * 60,
        )
        return url

    async def generate_download_signed_url(
        self,
        document_name: str,
        expiration_minutes: int = 15,
        mime_type: str | None = None,
        inline: bool = False,
    ) -> str:
        """Generate a presigned URL for download.

        Args:
            document_name: Name of the document.
            expiration_minutes: URL validity duration in minutes.
            mime_type: Optional Content-Type for response.
            inline: If True, use inline disposition instead of attachment.

        Returns:
            Presigned GET URL.

        Raises:
            FileNotFoundError: If document does not exist.
        """
        await self._ensure_clients()
        if not await self.document_exists(document_name):
            raise FileNotFoundError(f"Document '{document_name}' not found")
        key = self._get_key(document_name)
        filename = PurePosixPath(document_name).name
        disposition = (
            f'inline; filename="{filename}"'
            if inline
            else f'attachment; filename="{filename}"'
        )
        params = {
            "Bucket": self.bucket_name,
            "Key": key,
            "ResponseContentDisposition": disposition,
        }
        if mime_type:
            params["ResponseContentType"] = mime_type
        url = await self._public_client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiration_minutes * 60,
        )
        return url

    async def update_metadata(
        self,
        document_name: str,
        metadata: dict[str, str],
        overwrite_existing: bool = True,
        preserve_existing_keys: bool = True,
    ) -> None:
        """
        Update or set one or more metadata key-value pairs on an existing S3 object.

        Args:
            document_name: Name of the document (relative to doc_store_path)
            metadata: Dict of metadata keys → values to set/update
                     (keys are case-insensitive in S3, but usually lowercase)
            overwrite_existing: If False, raises ValueError if any key already exists
                                with a different value
            preserve_existing_keys: If True (default), keeps all existing metadata keys
                                    that are not being updated. If False, replaces the
                                    entire metadata set with only the provided keys.

        Raises:
            FileNotFoundError: If the object does not exist
            ValueError: If overwrite_existing=False and conflict detected
            ClientError: On S3 operation failure

        Example:
            await client.update_metadata(
                "projects/123/report.pdf",
                {"sha256": "abc123...", "processed-by": "v2.1", "tags": "final"},
                overwrite_existing=True
            )
        """
        await self._ensure_clients()

        head = await self._get_head_object(document_name=document_name)
        current_meta = head.get("Metadata", {}) or {}
        new_meta = self._create_metadata(
            current_metadata=current_meta,
            new_metadata=metadata,
            overwrite_existing=overwrite_existing,
            preserve_existing_keys=preserve_existing_keys,
        )

        key = self._get_key(document_name)
        copy_source = f"{self.bucket_name}/{key}"

        copy_kwargs = {
            "Bucket": self.bucket_name,
            "Key": key,
            "CopySource": copy_source,
            "Metadata": new_meta,
            "MetadataDirective": "REPLACE",
        }

        await self._private_client.copy_object(**copy_kwargs)

        updated_keys = ", ".join(metadata.keys())
        logger.debug(
            action=EventAction.WRITE,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.FILE,
            message=f"Updated metadata on {document_name}: {updated_keys}",
        )

    async def get_metadata(
        self,
        document_name: str,
        keys: list[str] | None = None,
        default: Any = None,
    ) -> dict[str, str]:
        """
        Retrieve metadata (or specific metadata keys) from an S3 object.

        Args:
            document_name: Name of the document (relative to doc_store_path)
            keys: Optional list of specific metadata keys to retrieve.
                  If None (default), returns the full metadata dictionary.
                  If provided, returns only the requested keys (as dict).
                  If a single string is passed, it is treated as a single key.
            default: Value to return for missing keys when requesting specific keys
                     (default: None)

        Returns:
            dict[str, str] of all metadata (may be empty)

        Raises:
            FileNotFoundError: If the object does not exist
            ClientError: On other S3 operation failures
        """
        await self._ensure_clients()

        head = await self._get_head_object(document_name=document_name)

        all_meta = head.get("Metadata", {}) or {}

        if keys is None:
            return all_meta

        if isinstance(keys, list):
            result = {}
            for key in keys:
                result[key] = all_meta.get(key, default)
            return result

        raise TypeError("keys must be str, list[str], or None")
