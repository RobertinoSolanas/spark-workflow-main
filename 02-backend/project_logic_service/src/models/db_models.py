"""SQLAlchemy database models for Project Logic Service."""

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase, AsyncAttrs):
    """SQLAlchemy declarative base."""

    __abstract__ = True

    def to_dict(self) -> dict:
        """Database model to serialized dict."""

        def serialize(value):
            if isinstance(value, uuid.UUID | datetime | date | enum.Enum):
                return str(value)
            return value

        return {
            col.name: serialize(getattr(self, col.name))
            for col in self.__table__.columns
        }


# --- Helper Mixins ---
class TimestampMixin:
    """Timestamp class to automatically create timestamps."""

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# --- Core Tables ---
class Applicant(Base, TimestampMixin):
    """Applicant (Antragsteller) model."""

    __tablename__ = "applicant"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Antragsstellenden Details (all nullable)
    salutation = Column(String, nullable=True)
    company = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    street = Column(String, nullable=True)
    house_number = Column(String, nullable=True)
    address_supplement = Column(String, nullable=True)
    plz = Column(String, nullable=True)
    location = Column(String, nullable=True)
    country = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    fax = Column(String, nullable=True)


class Project(Base, TimestampMixin):
    """Project model."""

    __tablename__ = "project"

    # Details
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)
    project_type_id = Column(UUID, ForeignKey("project_type.id"))
    created_by_id = Column(UUID)
    entry_date = Column(Date)
    internal_project_number = Column(String)
    applicant_id = Column(UUID, ForeignKey("applicant.id"), nullable=True)

    # Metadata
    status_id = Column(UUID, ForeignKey("project_status.id"))
    current_process_step_id = Column(UUID, ForeignKey("process_step.id"))

    # Relationships (only to models in this service)
    deadlines = relationship("Deadline", back_populates="project")
    applicant = relationship("Applicant", uselist=False)
    project_type = relationship("ProjectType", foreign_keys=[project_type_id])
    project_status = relationship("ProjectStatus", foreign_keys=[status_id])
    current_process_step = relationship(
        "ProcessStep", foreign_keys=[current_process_step_id]
    )


class Deadline(Base, TimestampMixin):
    """Deadline model."""

    __tablename__ = "deadline"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id"))
    start_at = Column(Date)
    end_at = Column(Date)
    deadline_type = Column(String)
    legal_basis = Column(String, nullable=True)

    project = relationship("Project", back_populates="deadlines")


# --- Process Steps ---
class ProcessStep(Base):
    """Process step model."""

    __tablename__ = "process_step"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_step_index = Column(Integer)
    project_type_id = Column(UUID, ForeignKey("project_type.id"))
    name = Column(String)

    # Relationships
    project_type = relationship("ProjectType", foreign_keys=[project_type_id])


# --- Types & Lookup Tables ---
class ProjectType(Base):
    """Project type lookup table."""

    __tablename__ = "project_type"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False)


class ProjectStatus(Base):
    """Project status lookup table."""

    __tablename__ = "project_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)
