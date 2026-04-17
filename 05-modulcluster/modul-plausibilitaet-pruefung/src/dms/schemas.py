from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DMSFileResponse(BaseModel):
    """
    Pydantic model representing a file response from the DMS API.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    filename: str
    bucket_path: str = Field(alias="bucketPath")
    project_id: str = Field(alias="projectId")
    mime_type: str | None = Field(default=None, alias="mimeType")
    workflow_id: str | None = Field(default=None, alias="workflowId")
    run_id: str | None = Field(default=None, alias="runId")
    vector_searchable: bool | None = Field(default=None, alias="vectorSearchable")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class DMSDocument(BaseModel):
    """Parameters for a DMS document."""

    project_id: str
    document_id: str
    document_name: str
    content_extraction_id: str


class ProjectBaseMetadataStatus(str, Enum):
    COMPLETE = "complete"
    FALLBACK_MISSING = "fallback_missing"


class BaseMetadata(BaseModel):
    application_id: str
    processing_timestamp: datetime
    project_applicant: str | None = None
    planned_project: str | None = None
    project_location: str | None = None
    affected_municipalities: list[str] | None = None
    affected_federal_states: list[str] | None = None
    planning_company: str | None = None
    application_subject: str | None = None
    pipeline_length: str | None = None
    pipeline_diameter: str | None = None
    application_receipt_date: str | None = None
    responsible_planning_authority: str | None = None

    @classmethod
    def fallback_unknown(cls, project_id: str) -> "BaseMetadata":
        return cls(
            application_id=project_id,
            processing_timestamp=datetime.now(UTC),
        )


class DocumentMetadata(BaseModel):
    """High-level metadata for a document."""

    document_id: str
    title: str | None = None
    summary: str | None = None


class ChunkMetadata(BaseModel):
    """Metadata associated with a document text chunk."""

    page_numbers: list[int] = Field(default_factory=list)
    chunk_type: str | None = None


class DocumentChunk(BaseModel):
    """Represents a specific segment of text from a document."""

    chunk_id: str
    parent_chunk_id: str | None
    page_content: str
    sub_chunks: list["DocumentChunk"] | None = Field(default_factory=list)
    metadata: ChunkMetadata


class DocumentDetailsResponse(BaseModel):
    """Raw response model for the document details API endpoint."""

    chunks: list[DocumentChunk] = Field(default_factory=list)
    metadata: DocumentMetadata


class DocDataResult(BaseModel):
    """Result model containing filtered document chunks and metadata."""

    dms_document: DMSDocument
    title: str | None
    chunks: list[DocumentChunk]
    summary: str | None = None
    error: str | None = None
