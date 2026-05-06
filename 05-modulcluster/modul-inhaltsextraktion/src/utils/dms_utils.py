# src/utils/dms_utils.py
"""
DMS (Document Management Service) storage utilities.

This module provides storage operations through the central DMS service,
which abstracts the underlying storage (GCS) and provides file management
via UUIDs.

Key differences from gcs_utils/s3_utils:
- DMS uses file_ids (UUIDs) instead of paths for most operations
- Uploads require project_id and file_type
- Downloads generate signed URLs internally
"""

import functools
import json
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from temporal import Base64Bytes
from temporalio import activity

from src.config import get_config
from src.env import ENV

# --- Pydantic Models ---


class CamelConfig:
    """Shared config for camelCase aliases and ORM mode."""

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class FileObject(BaseModel, CamelConfig):
    """File object returned by the DMS API."""

    id: UUID = Field(..., description="File UUID")
    type: str = Field(..., description="File type (document, content_extraction, etc.)")
    filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")
    bucket_path: PurePosixPath = Field(..., description="Full path in bucket")

    project_id: UUID | None = Field(None, description="Project scope")
    workflow_id: str | None = Field(None, description="Temporal workflow id")
    run_id: str | None = Field(None, description="Temporal run id")
    vector_searchable: bool | None = Field(None, description="If file is vectorized")

    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class FileUploadArgs(BaseModel, CamelConfig):
    """Arguments for uploading a file to DMS."""

    filename: str
    project_id: str
    type: str  # e.g., "document", "content_extraction"


# --- HTTP Client ---


def _json_default(obj: Any) -> Any:
    """Fallback serializer for json.dumps — handles UUID, datetime, etc."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


_json_serialize = functools.partial(json.dumps, default=_json_default)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Get or create the async HTTP client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(float(get_config().DMS_TIMEOUT)),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        activity.logger.info(f"Initialized DMS client (base_url: {ENV.DMS_BASE_URL})")
    return _client


async def _close_client() -> None:
    """Close the HTTP client (call on shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# --- Core DMS API Functions (file_id based) ---


async def get_file_metadata(file_id: UUID) -> FileObject:
    """
    Get metadata for a file by its ID.

    Args:
        file_id: The UUID of the file

    Returns:
        FileObject with file metadata

    Raises:
        FileNotFoundError: If file doesn't exist
        httpx.HTTPStatusError: For other HTTP errors
    """
    client = _get_client()
    url = f"{ENV.DMS_BASE_URL}/v2/files/{file_id}"

    response = await client.get(url)

    if response.status_code == 404:
        raise FileNotFoundError(f"DMS file not found: {file_id}")

    response.raise_for_status()
    return FileObject(**response.json())


async def download_file(file_id: str | UUID) -> bytes:
    """
    Download a file by its ID.

    Args:
        file_id: The UUID of the file

    Returns:
        File contents as bytes

    Raises:
        FileNotFoundError: If file doesn't exist
        httpx.HTTPStatusError: For other HTTP errors
    """
    client = _get_client()

    # Step 1: Generate download URL
    url = f"{ENV.DMS_BASE_URL}/v2/files/{file_id}/generate-download-url"
    response = await client.get(url)

    if response.status_code == 404:
        raise FileNotFoundError(f"DMS file not found: {file_id}")

    response.raise_for_status()
    response_data = response.json()
    download_url = response_data["downloadUrl"]  # camelCase from DMS API

    # Step 2: Download from the signed URL
    download_response = await client.get(download_url)
    download_response.raise_for_status()

    return download_response.content


async def download_file_as_stream(file_id: str) -> BytesIO:
    """
    Download a file by its ID as a BytesIO stream.

    Args:
        file_id: The UUID of the file

    Returns:
        File contents as BytesIO
    """
    content = await download_file(file_id)
    return BytesIO(content)


class ListFilesInput(BaseModel):
    project_id: UUID
    file_type: str = "document"
    page: int = 1
    page_size: int = 500


async def list_files(input: ListFilesInput) -> list[FileObject]:
    project_id = input.project_id
    file_type = input.file_type
    page = input.page
    page_size = input.page_size
    client = _get_client()
    url = f"{ENV.DMS_BASE_URL}/v2/files"
    params = {
        "projectId": str(project_id),
        "file_type": file_type,
        "page": page,
        "page_size": page_size,
    }

    response = await client.get(url, params=params)
    response.raise_for_status()

    return [FileObject(**file_data) for file_data in response.json()]


class DmsUploadInput(BaseModel):
    data: Base64Bytes
    filename: str
    project_id: UUID
    file_type: str = "content_extraction"
    content_type: str = "application/octet-stream"
    extra_params: dict[str, Any] | None = None


async def upload_file(
    input: DmsUploadInput,
) -> FileObject:
    client = _get_client()

    filename = input.filename
    project_id = input.project_id
    file_type = input.file_type
    content_type = input.content_type
    data = input.data

    # Step 1: Generate upload URL (POST request with JSON body)
    payload = {
        "filename": filename,
        "projectId": project_id,
        "type": file_type,
        "createNewVersion": True,
        **(input.extra_params or {}),
    }

    data_size_mb = len(data) / (1024 * 1024)

    try:
        url = f"{ENV.DMS_BASE_URL}/v2/files/generate-upload-url"
        activity.logger.info(f"DMS upload request: POST {url} with payload={payload}")
        response = await client.post(
            url,
            content=_json_serialize(payload),
            headers={"Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            activity.logger.error(f"DMS upload error: {response.status_code} - {response.text}")
        response.raise_for_status()
        upload_url = response.json()["uploadUrl"]  # camelCase from DMS API

        # Step 2: Upload to the signed URL
        upload_response = await client.put(upload_url, content=data, headers={"Content-Type": content_type})
        if upload_response.status_code >= 400:
            activity.logger.error(
                f"DMS signed URL upload error: {upload_response.status_code} - {upload_response.text}"
            )
        upload_response.raise_for_status()

        # Step 3: Confirm upload
        confirm_url = f"{ENV.DMS_BASE_URL}/v2/files/confirm-upload"
        confirm_response = await client.post(
            confirm_url,
            content=_json_serialize(payload),
            headers={"Content-Type": "application/json"},
        )
        if confirm_response.status_code >= 400:
            activity.logger.error(f"DMS confirm-upload error: {confirm_response.status_code} - {confirm_response.text}")
        confirm_response.raise_for_status()
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        # Re-raise as clean RuntimeError to prevent Temporal
        # "Failure exceeds size limit" — httpx exceptions capture the full
        # request body (which can be hundreds of MB for large documents).
        raise RuntimeError(
            f"DMS upload failed for '{filename}' ({data_size_mb:.1f} MB): {type(exc).__name__}: {exc}"
        ) from None

    return FileObject(**confirm_response.json())


async def delete_file(file_id: UUID) -> None:
    """
    Delete a file by its ID.

    Args:
        file_id: The UUID of the file

    Note:
        This is idempotent - doesn't raise error if file doesn't exist.
    """
    client = _get_client()
    url = f"{ENV.DMS_BASE_URL}/v2/files/{file_id}"

    response = await client.delete(url)

    # Don't raise on 404 - delete should be idempotent
    if response.status_code != 404:
        response.raise_for_status()
