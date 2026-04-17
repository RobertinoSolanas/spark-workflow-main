from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.db.enums import ProcessStep, SourceType


class SourceRef(BaseModel):
    """Nested source reference object."""

    type: SourceType
    item_id: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def validate_item_id(self) -> "SourceRef":
        """Enforce item_id is required when referencing a concrete domain object."""
        if self.type != SourceType.MANUAL and not self.item_id:
            raise ValueError(
                f"item_id is required for source type '{self.type.value}'"
            )
        return self


class CreateCommentRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    process_step: ProcessStep
    source_ref: SourceRef | None = None


class UpdateCommentRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    content: str | None = Field(None, min_length=1)
    process_step: ProcessStep | None = None
    source_ref: SourceRef | None = Field(
        None,
        description="Set to null to explicitly clear the source reference. Omit to leave unchanged.",
    )

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "UpdateCommentRequest":
        non_nullable = ("title", "content", "process_step")
        for field_name in non_nullable:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str
    content: str
    process_step: ProcessStep
    source_ref: SourceRef | None = None
    created_at: datetime
    updated_at: datetime
