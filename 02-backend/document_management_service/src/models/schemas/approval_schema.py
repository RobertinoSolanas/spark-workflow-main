from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.db.workflow_enum import ApprovalStatus


class CancelResponse(BaseModel):
    file_id: UUID
    success: bool


class ApprovalActionResponse(BaseModel):
    """Model representing an approval response."""

    status: Literal["success", "already_processed", "not_found"]
    message: str
    current_approval_status: ApprovalStatus | None = None


class FileChange(BaseModel):
    """Model representing a file change."""

    file_id: UUID
    bucket_path: str
    filename: str
    source_sha: str
    target_sha: str


class DeleteChange(BaseModel):
    """Model representing a file delete."""

    file_id: UUID
    filename: str
    sha: str


class Unchanged(BaseModel):
    """Model representing a file unchanged."""

    file_id: UUID
    filename: str
    sha: str


class RenameChange(BaseModel):
    """Model representing a rename change."""

    file_id: UUID
    old_name: str
    new_name: str
    sha: str


class NewFile(BaseModel):
    """Model representing new files change."""

    filename: str
    bucket_path: str
    sha: str


class FileDiffResponse(BaseModel):
    """Model representing project file diff."""

    new: list[NewFile] = Field(
        default_factory=list, description="List of newly added files"
    )
    deleted: list[DeleteChange] = Field(
        default_factory=list, description="List of files that were removed"
    )
    changed: list[FileChange] = Field(
        default_factory=list, description="List of files with content changes"
    )
    renamed: list[RenameChange] = Field(
        default_factory=list, description="List of files that were renamed"
    )
    unchanged: list[Unchanged] = Field(
        default_factory=list, description="List of files that remained unchanged"
    )
