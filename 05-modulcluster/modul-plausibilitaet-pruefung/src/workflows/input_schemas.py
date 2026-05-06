
from pydantic import BaseModel, Field


class OrchestratorInputSchema(BaseModel):
    """Base schema for workflow inputs."""
    project_id: str = Field(..., description="ID of the project associated with this workflow run.")
    document_ids: list[str] = Field(..., description="ID of the document to be processed.")
    classification_file_id: str | None = Field(None, description="DMS file ID for the classification output JSON, required for Qdrant workflow.")

class SingleDocumentWorkflowInputSchema(BaseModel):
    """Input schema for single document workflow."""
    project_id: str = Field(..., description="ID of the project associated with this workflow run.")
    document_id: str = Field(..., description="ID of the document to be processed.")
    is_erlaeuterungsbericht: bool = Field(False, description="Flag indicating if the document is an Erläuterungsbericht, which may require special handling in the workflow.")
