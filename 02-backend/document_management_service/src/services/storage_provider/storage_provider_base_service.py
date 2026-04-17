import hashlib
import io
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterable
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, BinaryIO

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
)

from src.config.settings import settings
from src.utils.logger import logger


class BaseStorageProviderService(ABC):
    """Storage provider abstract base class"""

    def __init__(
        self,
        bucket_name: str = settings.BUCKET_NAME,
        doc_store_path: str = settings.DOC_STORE_PATH,
        **_,
    ) -> None:
        """Initialize the DocumentService using S3-style object storage settings.

        Args:
            bucket_name (str): Name or URI of the storage bucket/container.
            doc_store_path (str): Subdirectory within the bucket to store documents.
            protocol (str, optional): Filesystem protocol ('s3', 'file', etc.).
                If omitted, inferred from `bucket_name`.
        """
        self.bucket_name = bucket_name
        self.doc_store_path = str(
            PurePosixPath(doc_store_path or "").as_posix().strip("/")
        )

        logger.debug(
            action=EventAction.NOTIFY,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.FILE,
            message=(
                f"Initializing Storage provider "
                f"bucket='{self.bucket_name}', path='{self.doc_store_path}'"
            ),
        )

    @abstractmethod
    async def initialize(self) -> None:
        """Enter async context for long-lived clients (call once at startup)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Exit async contexts (call once on shutdown)."""
        ...

    @abstractmethod
    async def bucket_exists(self) -> bool:
        """Check if a bucket exists."""
        ...

    @abstractmethod
    async def document_exists(self, document_name: str) -> bool:
        """Check whether a document exists.

        Args:
            document_name (str): Name of the document.

        Returns:
            bool: True if the document exists, False otherwise.
        """
        ...

    @abstractmethod
    async def get_file_mime_type(self, document_name: str) -> str:
        """Guess the MIME type based on file extension.

        Args:
            document_name (str): Name of the document.

        Returns:
            str: Guessed MIME type

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the MIME type is not set.
        """
        ...

    @abstractmethod
    async def delete_document(self, document_name: str) -> None:
        """Delete a document.

        Args:
            document_name (str): Name of the document to delete.

        Raises:
            FileNotFoundError: If the document does not exist.
        """
        ...

    @abstractmethod
    async def copy_document(
        self,
        source_name: str,
        destination_name: str,
        overwrite: bool = False,
    ) -> None:
        """
        Copy a document to a new name/path within the same storage backend.

        For cloud backends, this should be a fast server-side copy
        (metadata operation). For local filesystem, it's a normal file copy.

        Args:
            source_name: Original document name (relative to doc_store_path)
            destination_name: New document name (relative to doc_store_path)
            overwrite: If False, raise FileExistsError if destination already exists

        Raises:
            FileNotFoundError: If source does not exist
            FileExistsError: If destination exists and overwrite=False
        """
        ...

    @abstractmethod
    async def upload_document_from_obj(
        self,
        document_name: str,
        file_obj: BinaryIO,
        overwrite: bool = False,
        mime_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """
        Uploads a document from a file object.

        Args:
            document_name: The name of the document to upload
            file_obj: The file object to upload
            overwrite: If an existing file should be overwritten
            mime_type: The mime type of the file to upload
            metadata: Optional user metadata to store with the object
                  (keys and values must be strings).

        Returns:
            None
        """
        ...

    @abstractmethod
    async def download_document_as_file_obj(self, document_name: str) -> BytesIO:
        """Download a document into a BytesIO object.

        Args:
            document_name (str): Document name in storage.

        Returns:
            BytesIO: File-like object containing the document content.

        Raises:
            FileNotFoundError: If the document does not exist.
        """
        ...

    @abstractmethod
    async def download_document_stream(
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
        ...

    @abstractmethod
    async def list_all_documents(
        self,
        path: bool = False,
        prefix: str | None = None,
    ) -> list[str]:
        """
        List all documents within a path.

        Args:
            path: If only the path or the file name should be returned.
            prefix: The path prefix to list documents from.

        Returns:
            list[str]: List of document names or paths.
        """
        ...

    @abstractmethod
    async def generate_upload_signed_url(
        self,
        document_name: str,
        expiration_minutes: int = 15,
        mime_type: str | None = None,
    ) -> str:
        """
        Args:
            document_name (str): Document name.
            expiration_minutes (int): URL expiration in minutes.
            mime_type (str | None): Optional MIME type.

        Returns:
            str: A signed upload URL if supported by the backend.

        Abstract method to generate a signed URL for uploading a document.
        """
        ...

    @abstractmethod
    async def generate_download_signed_url(
        self,
        document_name: str,
        expiration_minutes: int = 15,
        mime_type: str | None = None,
        inline: bool = False,
    ) -> str:
        """
        Abstract method to generate a signed URL for downloading a document.

        Args:
            document_name (str): Document name.
            expiration_minutes (int): URL expiration in minutes.
            mime_type (str | None): Optional MIME type for response.
            inline (bool): Whether to display inline in browser.

        Returns:
            str: URL signed.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
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
        ...

    @staticmethod
    async def compute_sha256(
        source: BinaryIO | AsyncIterable[bytes],
        algorithm: str = "sha256",
        chunk_size: int = 8 * 1024 * 1024,
    ) -> str:
        """
        Compute hex digest of SHA-256 (or other hash) from either:
          - a seekable BinaryIO (BytesIO, file opened in rb mode, etc.)
          - an async iterable of bytes chunks

        Returns: hex string (64 characters for sha256)
        """
        hasher = hashlib.new(algorithm)

        if isinstance(source, io.IOBase):
            # Synchronous file-like object
            source.seek(0)  # make sure we start from beginning
            while chunk := source.read(chunk_size):
                hasher.update(chunk)
        else:
            # Async iterable (streaming source)
            async for chunk in source:
                hasher.update(chunk)

        return hasher.hexdigest()

    @staticmethod
    async def _create_metadata(
        current_metadata: dict[str, str],
        new_metadata: dict[str, str],
        overwrite_existing: bool,
        preserve_existing_keys: bool,
    ) -> dict[str, str]:
        """Helper method to create metadata dict."""
        if not overwrite_existing:
            for key, value in new_metadata.items():
                if key in current_metadata and current_metadata[key] != value:
                    raise ValueError(
                        f"Metadata key '{key}' already exists with different value "
                        f"(old: {current_metadata[key]!r}, new: {value!r})"
                    )

        if preserve_existing_keys:
            new_meta = current_metadata.copy()
            new_meta.update(new_metadata)
        else:
            new_meta = new_metadata.copy()

        return new_meta
