"""SQLAlchemy database models for Plausibility Notes Service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase, AsyncAttrs):
    """SQLAlchemy declarative base."""

    __abstract__ = True


class TimestampMixin:
    """Mixin to automatically create timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PlausibilityNote(Base, TimestampMixin):
    """Domain model storing plausibility notes (contradictions) per project."""

    __tablename__ = "plausibility_note"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")

    occurrences: Mapped[list[PlausibilityNoteOccurrence]] = relationship(
        "PlausibilityNoteOccurrence",
        back_populates="plausibility_note",
        cascade="all, delete-orphan",
    )


class PlausibilityNoteOccurrence(Base, TimestampMixin):
    """Occurrences of a plausibility note (contradiction) in documents."""

    __tablename__ = "plausibility_note_occurrence"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plausibility_note_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plausibility_note.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[str] = mapped_column(String, nullable=False)
    document_name: Mapped[str | None] = mapped_column(String, nullable=True)
    content_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    plausibility_note: Mapped[PlausibilityNote] = relationship(
        "PlausibilityNote", back_populates="occurrences"
    )
