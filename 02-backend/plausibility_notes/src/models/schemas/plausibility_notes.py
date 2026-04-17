"""Pydantic schemas for plausibility note operations."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class PlausibilityNoteStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class ContradictionOccurrence(BaseModel):
    document_id: str
    document_name: str | None = None
    content_excerpt: str
    page_number: int | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Contradiction(BaseModel):
    id: UUID
    description: str
    status: PlausibilityNoteStatus
    occurrences: list[ContradictionOccurrence]

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PlausibilityCheckResult(BaseModel):
    contradictions: list[Contradiction]

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class JobDoneRequest(BaseModel):
    file_id: UUID = Field(
        ..., description="File ID pointing to the data.json with results"
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FileDownloadResponse(BaseModel):
    """Presigned URL for downloading a file."""

    download_url: str = Field(..., description="Presigned download URL")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SuccessResponse(BaseModel):
    success: bool = Field(
        True, description="Indicates whether the operation was successful"
    )


class JobDoneResponse(BaseModel):
    """Response for the plausibility job-done endpoint."""

    status: str
    contradictions_found: int
    total_occurrences: int
    previous_records_deleted: int


class UpdateNoteRequest(BaseModel):
    status: PlausibilityNoteStatus

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
