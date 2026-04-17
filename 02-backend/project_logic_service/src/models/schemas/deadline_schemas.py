from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DeadlineResponse(BaseModel):
    """Response model for deadline metadata."""

    id: UUID = Field(...)
    project_id: UUID = Field(..., alias="projectId")
    start_at: date = Field(..., alias="startAt")
    end_at: date = Field(..., alias="endAt")
    deadline_type: str = Field(..., alias="deadlineType")
    legal_basis: str | None = Field(None, alias="legalBasis")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class CreateDeadlineRequest(BaseModel):
    """Pydantic model for create deadline request."""

    project_id: UUID = Field(..., alias="projectId")
    start_at: date = Field(..., alias="startAt")
    end_at: date = Field(..., alias="endAt")
    deadline_type: str = Field(..., alias="deadlineType")
    legal_basis: str | None = Field(None, alias="legalBasis")

    @model_validator(mode="after")
    def validate_dates(self) -> "CreateDeadlineRequest":
        """Validates model deadline start and end date."""
        if self.start_at > self.end_at:
            raise ValueError("startAt must be less than or equal to endAt")
        return self

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "projectId": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380010",
                    "startAt": "2026-08-04",
                    "endAt": "2027-08-04",
                    "deadlineType": "Frist",
                    "legalBasis": "§ 5 Absatz 1 Satz 2 BGB",
                }
            ]
        },
    }


class UpdateDeadlineRequest(BaseModel):
    """Pydantic model for updated deadline metadata."""

    start_at: date | None = Field(None, alias="startAt")
    end_at: date | None = Field(None, alias="endAt")
    deadline_type: str | None = Field(None, alias="deadlineType")
    legal_basis: str | None = Field(None, alias="legalBasis")

    @model_validator(mode="after")
    def validate_dates(self) -> "UpdateDeadlineRequest":
        """Validates model deadline start and end date."""
        if self.start_at and self.end_at and self.start_at > self.end_at:
            raise ValueError("start_at must be less than or equal to end_at")
        return self

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "startAt": "2026-08-04",
                    "endAt": "2027-08-04",
                    "deadlineType": "Frist",
                    "legalBasis": "§ 5 Absatz 1 Satz 2 BGB",
                }
            ]
        },
    }
