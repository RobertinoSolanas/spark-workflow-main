from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.models.db.file_enum import FileTypeEnum
from src.models.db.workflow_enum import WorkflowStatusEnum


class CamelConfig:
    """Shared config for camelCase aliases and ORM mode."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


# Scoping mixins
class ProjectScopedMixin(BaseModel):
    """Files that belong to a specific project."""

    project_id: UUID = Field(..., description="ID of the project")


class OptionalProjectScopedMixin(BaseModel):
    """Files that optionally belong to a specific project."""

    project_id: UUID | None = Field(None, description="ID of the project")


class TemporalScopedMixin(BaseModel):
    """Files scoped to a Temporal workflow execution."""

    workflow_id: str = Field(..., description="Temporal workflow ID")
    run_id: str = Field(..., description="Temporal run ID")


class BaseFileUpload(BaseModel):
    """Base model for upload requests."""

    filename: str = Field(..., description="File name")
    create_new_version: bool = Field(
        False, description="Create new version if file already exists"
    )

    model_config = ConfigDict(
        **CamelConfig.model_config,
        json_schema_extra={
            "examples": [
                {
                    "type": "document",
                    "projectId": "00000000-0000-0000-0000-000000000000",
                    "filename": "contract.pdf",
                    "createNewVersion": False,
                }
            ]
        },
    )


# Concrete upload models
class ProjectDocumentUpload(BaseFileUpload, ProjectScopedMixin):
    """Presigned upload request for a project document."""

    type: Literal[FileTypeEnum.DOCUMENT.value] = Field(  # type: ignore
        ..., description="Must be 'document'"
    )


class ProjectZipUpload(BaseFileUpload, ProjectScopedMixin):
    """Presigned upload request for a project zip file."""

    type: Literal[FileTypeEnum.ZIP.value] = Field(  # type: ignore
        ..., description="Must be 'zip'"
    )


class ContentExtractionUpload(BaseFileUpload, ProjectScopedMixin):
    """Internal upload of extracted content for a project document."""

    type: Literal[FileTypeEnum.CONTENT_EXTRACTION.value] = Field(  # type: ignore
        ..., description="Internal content extraction result"
    )


class TemplateUpload(BaseFileUpload, OptionalProjectScopedMixin):
    """Presigned upload request for a global template."""

    type: Literal[FileTypeEnum.TEMPLATE.value] = Field(  # type: ignore
        ..., description="Must be 'template'"
    )


class LawDataUpload(BaseFileUpload):
    """Direct upload of global law/reference data files."""

    type: Literal[FileTypeEnum.LAW_DATA.value] = Field(  # type: ignore
        ..., description="Global law data file"
    )


class TemporalCheckpointUpload(
    BaseFileUpload, TemporalScopedMixin, OptionalProjectScopedMixin
):
    """Internal checkpoint file for Temporal workflow execution."""

    type: Literal[FileTypeEnum.TEMPORAL_CHECKPOINT.value] = Field(  # type: ignore
        ..., description="Temporal workflow checkpoint"
    )


# Discriminated union
UploadRequest = Annotated[
    ProjectDocumentUpload
    | ProjectZipUpload
    | ContentExtractionUpload
    | LawDataUpload
    | TemporalCheckpointUpload
    | TemplateUpload,
    Field(discriminator="type"),
]


# Response models
class FileDownloadResponse(BaseModel, CamelConfig):
    """Presigned URL for downloading a file."""

    download_url: str = Field(
        ..., description="Presigned download URL (expires in 5 min)"
    )


class FileUploadUrlResponse(BaseModel, CamelConfig):
    """Presigned URL and expected MIME type for upload."""

    upload_url: str = Field(..., description="Presigned PUT URL")
    mime_type: str = Field(..., description="Expected MIME type (e.g. application/pdf)")


class FileUpdateRequest(BaseModel, CamelConfig):
    """Request to update mutable file properties (admin/internal only)."""

    mime_type: str | None = Field(None, description="Override detected MIME type")
    vector_searchable: bool | None = Field(None, description="If file is vectorized")
    filename: str | None = Field(None, description="File name")


class StartFileProcessingRequest(BaseModel):
    """Request to validate and process an uploaded ZIP via Temporal."""

    model_config = ConfigDict(
        **CamelConfig.model_config,
        extra="forbid",
    )

    file_id: UUID = Field(..., description="Uploaded file ID")
    project_id: UUID = Field(..., description="Project ID")


class StartFileProcessingResponse(BaseModel, CamelConfig):
    """Response with Temporal workflow identifiers for polling."""

    workflow_id: str = Field(..., description="Temporal workflow ID")
    run_id: str = Field(..., description="Temporal run ID")
    workflow_status: WorkflowStatusEnum = Field(
        ..., description="Current processing status for this ZIP upload"
    )


class ZipFileResponse(BaseModel, CamelConfig):
    """Complete zip file metadata returned to clients."""

    id: UUID = Field(..., description="Zip file UUID")
    filename: str = Field(..., description="Original filename")
    bucket_path: PurePosixPath = Field(..., description="Full path in bucket")
    project_id: UUID = Field(..., description="Project ID")
    workflow_status: WorkflowStatusEnum = Field(
        ..., description="Processing workflow status for this ZIP upload"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class FileResponse(BaseModel, CamelConfig):
    """Complete file metadata returned to clients."""

    id: UUID = Field(..., description="File UUID")
    type: FileTypeEnum = Field(..., description="File type")
    filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")
    bucket_path: PurePosixPath = Field(..., description="Full path in bucket")
    version: int = Field(..., description="File version")

    project_id: UUID | None = Field(None, description="Project scope")
    workflow_id: str | None = Field(None, description="Temporal workflow id")
    run_id: str | None = Field(None, description="Temporal run id")
    vector_searchable: bool | None = Field(None, description="If file is vectorized")

    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
