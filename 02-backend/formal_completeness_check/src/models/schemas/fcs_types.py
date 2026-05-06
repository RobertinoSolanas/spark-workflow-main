from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class SuccessResponse(BaseModel):
    """Generic success response for simple operations."""

    success: bool = Field(
        True, description="Indicates whether the operation was successful"
    )


class DocumentTypeDefinition(BaseModel):
    """Schema for defining a document type for matching.

    This model holds the metadata for a specific document type found in the
    requirements list, including its category, official name, and a semantic
    description used for the matching logic.

    Attributes:
        category (Optional[str]): The supercategory (e.g., 'Environmental Part')
            for better structuring.
        document_type_name (str): The official designation of the document
            (e.g., 'Explanatory Report').
        document_type_description (str): A concise description of the document's
            content and purpose, used for semantic matching.
    """

    category: str | None = Field(
        None,
        description="Die Oberkategorie (z.B. 'Umweltfachlicher Teil') zur besseren Strukturierung.",
    )

    document_type_name: str = Field(
        ...,
        description="Die offizielle Bezeichnung der Unterlage (z.B. 'Erläuterungsbericht').",
    )
    document_type_description: str = Field(
        ...,
        description="Eine prägnante Beschreibung des Inhalts und Zwecks des Dokuments, genutzt für das semantische Matching.",
    )


class AssignedDocument(BaseModel):
    """Final output representation of an assigned document within a category.

    Attributes:
        document_id (UUID): The ID of the document file.
        document_name (str): The name of the document file.
        reasoning (str): The explanation provided by the LLM for this assignment.
        confidence (float): The confidence score (0.0 to 1.0) of the assignment.
        ai_suggested_required_document_type_id: The AI-suggested document type ID.
        human_required_document_type_id: The human-assigned document type ID (overrides AI if set).
        content_extraction_id: The extraction ID of the document content in the DMS.
    """

    document_id: UUID
    document_name: str
    reasoning: str
    confidence: float
    ai_suggested_required_document_type_id: UUID | None = None
    human_required_document_type_id: UUID | None = None
    content_extraction_id: UUID | None = None


class UnassignedDocument(BaseModel):
    """Represents a document that could not be matched to any document type.

    Attributes:
        document_id (UUID): The ID of the document file.
        document_name (str): The name of the document file.
        reasoning (str): The explanation provided by the LLM for why this document is unassigned.
        confidence (float): The confidence score (0.0 to 1.0) of the non-assignment.
        ai_suggested_required_document_type_id: Always None for unassigned documents.
        human_required_document_type_id: The human-assigned document type ID if set.
        content_extraction_id: The extraction ID of the document content in the DMS.
    """

    document_id: UUID
    document_name: str
    reasoning: str
    confidence: float
    ai_suggested_required_document_type_id: UUID | None = None
    human_required_document_type_id: UUID | None = None
    content_extraction_id: UUID | None = None


class MatchedDocumentTypeOutput(BaseModel):
    """Represents a specific document type definition and the files assigned to it.

    Attributes:
        required_document_type (DocumentTypeDefinition): The definition of the
            document type from the requirements list.
        assigned_documents (List[AssignedDocument]): A list of structured
            outputs for documents that have been matched to this document type.
        confidence (float): The confidence score (0.0 to 1.0) for the document type match.
    """

    required_document_type: DocumentTypeDefinition
    assigned_documents: list[AssignedDocument]
    confidence: float = Field(
        ...,
        description="The confidence score (0.0 to 1.0) for the document type match.",
    )


class FormalCompletenessCheckResults(BaseModel):
    """The final output of the LLM matching workflow.

    Attributes:
        matched_document_types (list[MatchedDocumentTypeOutput]): A list of
            document types that were successfully matched with one or more files.
        unassigned_documents (list[UnassignedDocument]): A list of documents that
            could not be confidently matched to any document type.
    """

    matched_document_types: list[MatchedDocumentTypeOutput]
    unassigned_documents: list[UnassignedDocument]


class JobDoneRequest(BaseModel):
    """Request payload for the job-done endpoint."""

    file_id: UUID = Field(
        ..., description="File ID pointing to the data.json with results"
    )


class JobDoneResponse(BaseModel):
    """Response for the job-done endpoint."""

    status: str
    matched_document_types: int
    assigned_documents: int
    unassigned_documents: int
    previous_records_deleted: int


class TemplateDocumentTypeResponse(BaseModel):
    """A template document type with its category, used for listing required documents."""

    category: str
    document_type_id: UUID
    document_type_name: str
    document_type_description: str
    expected_count: int | None


class RequiredDocumentResponse(BaseModel):
    """A single required document type within a category."""

    document_type_id: UUID
    document_name: str
    origin: Literal["system", "custom"]
    is_resolved: bool


class CategoryRequiredDocumentsResponse(BaseModel):
    """A category with its required document types."""

    category_id: UUID
    category_name: str
    required_documents: list[RequiredDocumentResponse]


class RequiredDocumentTypesResponse(BaseModel):
    """Wrapper for the required document types endpoint."""

    categories: list[CategoryRequiredDocumentsResponse]


class CreateRequiredDocumentTypeRequest(BaseModel):
    """Request payload for creating a custom required document type."""

    document_name: str


class PatchRequiredDocumentTypeRequest(BaseModel):
    """Request payload for partially updating a required document type."""

    document_name: str | None = None
    is_resolved: bool | None = None


class DocumentAssignmentItem(BaseModel):
    """AI vs human document type assignment for a single file."""

    file_id: UUID
    ai_suggested_required_document_type_id: UUID | None
    human_required_document_type_id: UUID | None


class DocumentAssignmentsResponse(BaseModel):
    """Response for the document-assignments endpoint."""

    items: list[DocumentAssignmentItem]


class PatchDocumentByFileIdRequest(BaseModel):
    """Request payload for patching the human assignment on a document."""

    human_required_document_type_id: UUID | None = None


class FileDownloadResponse(BaseModel):
    """Presigned URL for downloading a file."""

    download_url: str = Field(
        ..., description="Presigned download URL", alias="downloadUrl"
    )

    model_config = ConfigDict(populate_by_name=True)
