"""SQLAlchemy database models for Formal Completeness Check Service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql.schema import ForeignKeyConstraint


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


class Category(Base, TimestampMixin):
    """Category for grouping document types per project."""

    __tablename__ = "category"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_category_project_name"),
        UniqueConstraint("id", "project_id", name="uq_category_id_project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    document_types: Mapped[list[DocumentType]] = relationship(
        "DocumentType",
        back_populates="category",
        cascade="all, delete-orphan",
        foreign_keys="[DocumentType.category_id, DocumentType.project_id]",
    )


class DocumentType(Base, TimestampMixin):
    """Required document type definitions per project."""

    __tablename__ = "document_type"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_document_type_project_name"),
        UniqueConstraint("id", "project_id", name="uq_document_type_id_project_id"),
        ForeignKeyConstraint(
            ["category_id", "project_id"],
            ["category.id", "category.project_id"],
            ondelete="SET NULL",
        ),
        CheckConstraint("origin IN ('system', 'custom')", name="chk_document_type_origin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    origin: Mapped[str] = mapped_column(String, nullable=False, default="system")

    category: Mapped[Category | None] = relationship(
        "Category",
        back_populates="document_types",
        foreign_keys=[category_id, project_id],
    )

    assigned_documents: Mapped[list[Document]] = relationship(
        "Document",
        back_populates="document_type",
        cascade="all, delete-orphan",
        foreign_keys="[Document.ai_suggested_required_document_type_id, Document.project_id]",
    )


class Document(Base, TimestampMixin):
    """Table for assigned and unassigned documents."""

    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    content_extraction_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ai_suggested_required_document_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    document_name: Mapped[str] = mapped_column(String, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    human_required_document_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "document_type.id",
            name="fk_document_human_required_document_type",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    document_type: Mapped[DocumentType | None] = relationship(
        "DocumentType",
        back_populates="assigned_documents",
        foreign_keys=[ai_suggested_required_document_type_id, project_id],
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["ai_suggested_required_document_type_id", "project_id"],
            ["document_type.id", "document_type.project_id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_document_project_file_id",
            "project_id",
            "file_id",
            unique=True,
            postgresql_where=text("file_id IS NOT NULL"),
        ),
    )


class TemplateCategory(Base, TimestampMixin):
    """Template category for seeding project-specific categories."""

    __tablename__ = "template_category"
    __table_args__ = (
        Index(
            "uq_template_category_project_type_name",
            "project_type_id",
            "name",
            unique=True,
            postgresql_where=text("deleted IS NOT TRUE"),
            sqlite_where=text("deleted IS NOT TRUE"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    project_type_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    template_document_types: Mapped[list[TemplateDocumentType]] = relationship(
        "TemplateDocumentType",
        back_populates="template_category",
        cascade="all, delete-orphan",
    )


class TemplateDocumentType(Base, TimestampMixin):
    """Template document type for seeding project-specific document types."""

    __tablename__ = "template_document_type"
    __table_args__ = (
        Index(
            "uq_template_document_type_category_name",
            "template_category_id",
            "name",
            unique=True,
            postgresql_where=text("deleted IS NOT TRUE"),
            sqlite_where=text("deleted IS NOT TRUE"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_category_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("template_category.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    template_category: Mapped[TemplateCategory] = relationship(
        "TemplateCategory",
        back_populates="template_document_types",
    )


class ProjectTemplateVersion(Base, TimestampMixin):
    """Tracks project to project_type registration for template lookup."""

    __tablename__ = "project_template_version"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_template_version_project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    project_type_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TableOfContentNotes(Base, TimestampMixin):
    """From Agent extracted table of content files"""

    __tablename__ = "table_of_content_notes"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
