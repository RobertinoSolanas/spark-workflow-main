from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlausibilityOrchestratorInput(BaseModel):
    """Input for the PlausibilityMainOrchestratorWorkflow."""

    project_id: str = Field(..., description="ID of the project associated with this workflow run.")
    document_ids: list[str] = Field(..., description="IDs of the documents to be processed.")
    classification_file_id: str | None = Field(
        None, description="DMS file ID for the classification output JSON, required for Qdrant workflow."
    )


class DMSFileResponse(BaseModel):
    """Pydantic model representing a file response from the DMS API."""

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
