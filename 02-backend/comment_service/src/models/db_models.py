"""SQLAlchemy database models."""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.models.db.enums import ProcessStep, SourceType


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Return enum values for SQLAlchemy enum persistence."""
    return [member.value for member in enum_cls]


class Base(DeclarativeBase, AsyncAttrs):
    """SQLAlchemy declarative base."""

    __abstract__ = True


class TimestampMixin:
    """Timestamp mixin to automatically create timestamps."""

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


class Comment(Base, TimestampMixin):
    """Comment model."""

    __tablename__ = "comment"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    process_step: Mapped[ProcessStep] = mapped_column(
        SAEnum(ProcessStep, values_callable=_enum_values, name="commentprocessstep"),
        nullable=False,
    )
    source_type: Mapped[SourceType | None] = mapped_column(
        SAEnum(SourceType, values_callable=_enum_values, name="commentsourcetype"),
        nullable=True,
    )
    source_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_comment_project_id", "project_id"),
        Index("ix_comment_project_process_step", "project_id", "process_step"),
    )
