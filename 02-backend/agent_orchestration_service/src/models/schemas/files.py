from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.schemas.config import CamelConfig


class FileUploadArgs(BaseModel, CamelConfig):
    """File upload arguments for the API."""

    type: str
    filename: str | None = Field(None, description="Filename")
    project_id: str | None = Field(None, description="Project id")
    workflow_id: str | None = Field(None, description="Temporal workflow id")
    run_id: str | None = Field(None, description="Temporal run id")


class FileObject(BaseModel, CamelConfig):
    """File object returned by the API."""

    id: UUID = Field(..., description="File UUID")
    type: str = Field(..., description="File type")
    filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")
    bucket_path: PurePosixPath = Field(..., description="Full path in bucket")

    project_id: UUID | None = Field(None, description="Project scope")
    workflow_id: str | None = Field(None, description="Temporal workflow id")
    run_id: str | None = Field(None, description="Temporal run id")
    vector_searchable: bool | None = Field(None, description="If file is vectorized")

    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
