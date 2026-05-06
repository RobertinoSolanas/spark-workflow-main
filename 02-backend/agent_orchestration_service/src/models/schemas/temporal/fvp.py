from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FVPWorkflowRequest(BaseModel):
    project_id: str


class FVPWorkflowArgs(BaseModel):
    project_id: str


class DocumentTypeDefinition(BaseModel):
    category: str | None = Field(None)
    document_type_name: str
    document_type_description: str


class FullFVPWorkflowInput(BaseModel):
    project_id: str
    file_ids: list[str]
    document_types: list[DocumentTypeDefinition]


class SendFVPResultsActivityArgs(BaseModel):
    project_id: str
    file_id: str


class SendPlausibilityResultsActivityArgs(BaseModel):
    project_id: str
    file_id: str


class FVPExtractionWorkflowResultItem(BaseModel):
    workflow_type: str
    result: dict[str, Any] | None = None
    error: str | None = None


class FVPExtractionWorkflowResult(BaseModel):
    results: list[FVPExtractionWorkflowResultItem]


class TOCMatchingWorkflowArgs(BaseModel):
    project_id: str


class SendTOCMatchingResultsActivityArgs(BaseModel):
    project_id: str
    file_id: str


class TemplateDocumentTypeResponse(BaseModel):
    """A template document type with its category, used for listing required documents."""

    category: str
    document_type_id: UUID
    document_type_name: str
    document_type_description: str
    expected_count: int | None
