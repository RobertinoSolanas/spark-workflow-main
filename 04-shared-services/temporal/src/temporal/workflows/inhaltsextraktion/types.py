from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field
from temporal.utils import WorkflowName

PROCESS_DOCUMENTS_WORKFLOW_ID = WorkflowName("process-documents-workflow")


class BaseMetadata(BaseModel):
    """Base metadata extracted from a priority document (e.g., Erläuterungsbericht)."""

    application_id: str
    processing_timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    project_applicant: str | None = None
    planned_project: str | None = None
    project_location: str | None = None
    affected_municipalities: list[str] = Field(default_factory=list)
    affected_federal_states: list[str] = Field(default_factory=list)
    planning_company: str | None = None
    application_subject: str | None = None
    pipeline_length: str | None = None
    pipeline_diameter: str | None = None
    application_receipt_date: str | None = None
    responsible_planning_authority: str | None = None


class ProcessedFileInfo(BaseModel):
    """Information about a single processed document file."""

    document_name: str
    document_path: str
    processed_json_file_id: str


class SummaryData(BaseModel):
    """Typed structure for the summary.json content."""

    base_metadata: BaseMetadata | None = None
    total_duration_seconds: float
    processed_files: list[ProcessedFileInfo]


class ProcessDocumentsWorkflowInput(BaseModel):
    """Input for the document processing workflow."""

    file_ids: list[UUID]
    project_id: UUID
    skip_qdrant: bool = False
    skip_pageindex: bool = False


class ProcessDocumentsWorkflowOutput(BaseModel):
    """Output from the document processing workflow."""

    summary_file_id: UUID
    summary_data: SummaryData
    processed_file_ids: list[UUID]
    qdrant_ok: bool = False
    qdrant_processed_ids: list[str] = []
    qdrant_failed_ids: list[str] = []
    pageindex_ok: bool = False
    pageindex_created_files: int = 0
