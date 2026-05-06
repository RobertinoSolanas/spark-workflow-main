from uuid import UUID

from pydantic import BaseModel, Field


class ProcessStepResponse(BaseModel):
    """Pydantic model for process steps schema."""

    id: UUID
    name: str = Field(...)
    project_type_id: UUID = Field(..., alias="projectTypeId")
    process_step_index: int = Field(..., alias="processStepIndex")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
