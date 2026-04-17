from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql.expression import text
from sqlalchemy.sql.sqltypes import JSON

from src.models.db.file_enum import FileTypeEnum
from src.models.db.workflow_enum import WorkflowStatusEnum

jsonb = JSONB if "postgresql" in str(text("1")) else JSON


class Base(DeclarativeBase, AsyncAttrs):
    """SQLAlchemy declarative base."""

    __abstract__ = True


class TimestampMixin:
    """Mixin to automatically create timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class File(Base, TimestampMixin):
    """Table for storing file metadata with flexible optional metadata."""

    __tablename__ = "file"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type: Mapped[FileTypeEnum] = mapped_column(
        Enum(FileTypeEnum), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String, nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    bucket_path: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )

    # Optional fields
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    workflow_id: Mapped[str | None] = mapped_column(String, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    vector_searchable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_zip_file_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("zip_file.id"), nullable=True, index=True
    )

    # Soft delete
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    source_zip_file: Mapped[ZipFile | None] = relationship(
        "ZipFile", back_populates="files"
    )

    __table_args__ = (
        Index(
            "ix_files_type_project",
            "type",
            "project_id",
        ),
        UniqueConstraint(
            "project_id",
            "type",
            "filename",
            "source_zip_file_id",
            name="uq_file_zip_entry_source",
        ),
    )


class ZipFile(Base, TimestampMixin):
    """Table for storing zip file metadata."""

    __tablename__ = "zip_file"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filename: Mapped[str] = mapped_column(String, nullable=False, index=True)
    bucket_path: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    workflow_status: Mapped[WorkflowStatusEnum] = mapped_column(
        Enum(
            WorkflowStatusEnum,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="workflowstatusenum",
        ),
        nullable=False,
        default=WorkflowStatusEnum.PENDING,
        server_default=WorkflowStatusEnum.PENDING.value,
        index=True,
    )

    files: Mapped[list[File | None]] = relationship(
        "File", back_populates="source_zip_file", cascade="all, delete-orphan"
    )
