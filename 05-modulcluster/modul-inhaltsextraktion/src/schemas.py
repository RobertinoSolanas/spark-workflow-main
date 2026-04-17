"""
Shared Pydantic models used by workflows, activities, and processors.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl
from temporal import Base64Bytes
from temporal.workflows.inhaltsextraktion.types import BaseMetadata

from src.providers.base import ContentItemDict


class ExtractionOutput(BaseModel):
    """
    Unified output from any extraction provider.

    This is the canonical result type for document extraction activities.
    Contains markdown content, structural content list, and image references.

    Attributes:
        markdown: Extracted markdown content (custom format with <TABELLE>/<BILD> tags)
        content_list: Structural content list (unified format, used as Dict)
        image_bytes: Dict mapping image filenames to raw image bytes
        image_refs: Dict mapping image filenames to DMS file_ids (lightweight refs
            uploaded per-chunk during extraction to avoid carrying GB of image bytes
            through Temporal payloads). When populated, image_bytes may be empty.
    """

    markdown: str = ""
    content_list: list[ContentItemDict] = []
    image_bytes: dict[str, Base64Bytes] = {}
    image_refs: dict[str, str] = {}  # filename -> DMS file_id


class DocumentProcessRequest(BaseModel):
    """Request model for processing a document based on the new payload."""

    id: str = Field(..., description="Unique identifier for the document.")
    originalFileName: str = Field(
        ..., description="The original filename of the document."
    )
    mimeType: str = Field(..., description="The MIME type of the document.")
    bucketPath: str = Field(..., description="The GCS path to the document.")
    projectId: str = Field(..., description="The project identifier.")
    vectorSearchable: bool | None = None
    createdAt: datetime
    updatedAt: datetime
    requested: bool | None = None
    callbackUrl: HttpUrl | None = Field(
        None, description="The URL to the callback service."
    )


class ProcessDocumentRequest(BaseModel):
    """Request model for processing a document."""

    file_path: str = Field(
        ..., description="The GCS path to the document to be processed."
    )
    output_dir: str = Field(
        ..., description="The GCS directory where results should be saved."
    )
    process_images: bool = Field(
        True, description="Flag to enable/disable image processing."
    )


class ProcessDocumentResponse(BaseModel):
    """Response model for a successfully processed document."""

    message: str = Field(
        "Processing started successfully.", description="Status message."
    )
    output_path: str = Field(
        ..., description="The GCS path where the processed output is stored."
    )


class SubChunk(BaseModel):
    """Represents a sub-chunk of a larger document chunk."""

    chunk_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    parent_chunk_id: uuid.UUID | None = None
    page_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    header: str | None = None


class Chunk(BaseModel):
    """Represents a chunk of the document, split by headers."""

    chunk_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    parent_chunk_id: uuid.UUID | None = None
    page_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    sub_chunks: list[SubChunk] = Field(default_factory=list)
    header: str | None = None


class DocumentTypeInfo(BaseModel):
    """Nested document type classification result with provenance tracking."""

    name: str | None = None
    category: str | None = None
    description: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    source: str = "ai"  # "ai" or "user"


class Metadata(BaseModel):
    """Represents the final, assembled metadata for a processed document."""

    document_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the document.",
    )
    original_document_name: str = Field(
        ..., description="The original filename of the document."
    )
    source_file_id: str | None = Field(
        None,
        description="DMS file_id of the original source document (e.g. the uploaded PDF).",
    )
    document_type: DocumentTypeInfo | None = Field(
        None,
        description="Nested document type classification with provenance.",
    )
    pages: int | None = Field(
        None, description="The total number of pages in the document."
    )
    base_metadata_status: str | None = Field(
        None,
        description="Status of the base metadata extraction (Erläuterungsbericht).",
    )
    base_metadata: BaseMetadata | None = Field(
        None,
        description=(
            "The extracted metadata from the priority document (Erläuterungsbericht)."
        ),
    )
    summary: str | None = Field(
        None, description="A generated summary of the document’s content."
    )
    processing_duration_seconds: float | None = Field(
        None, description="The time in seconds it took to process the document."
    )

    project_id: str | None = None


class ProcessedDocument(BaseModel):
    """Represents the final processed document including content and metadata."""

    metadata: Metadata
    markdown_content: str
    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The markdown content split into chunks by headers.",
    )


class Topic(BaseModel):
    """Schema for a single topic."""

    id: int
    name: str
    description: str


class ProcessDocumentsDmsRequest(BaseModel):
    """Request model for processing documents via DMS."""

    file_ids: list[UUID] = Field(
        ...,
        description="List of DMS file IDs (UUIDs) to process.",
    )
    project_id: UUID = Field(
        ...,
        description="Project identifier (UUID).",
    )
