from uuid import UUID

from pydantic import BaseModel
from temporal.workflows.inhaltsextraktion.types import BaseMetadata


class SingleDocumentWorkflowOutput(BaseModel):
    """
    Output from processing a single document.
    """

    final_json_file_id: UUID  # DMS file_id of the _processed.json
    file_id: str = ""  # Original DMS file_id of the source document
    base_metadata: BaseMetadata | None = None
    document_name: str = "unknown"
    document_path: str = ""
