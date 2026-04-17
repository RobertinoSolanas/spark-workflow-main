from uuid import UUID

from pydantic import BaseModel, Field


class ProjectTypeResponse(BaseModel):
    """Pydantic model for project type response."""

    id: UUID
    name: str

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class CreateProjectTypeRequest(BaseModel):
    """Pydantic model for creating a project type."""

    name: str = Field(min_length=1, max_length=255)


class UpdateProjectTypeRequest(BaseModel):
    """Pydantic model for updating a project type."""

    id: UUID
    name: str = Field(min_length=1, max_length=255)
