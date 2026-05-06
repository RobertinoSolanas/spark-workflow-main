"""Initial schema migration for Project Logic Service

Revision ID: 001_initial
Revises:
Create Date: 2025-01-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial schema for Project Logic Service."""
    # Create project_type table
    op.create_table(
        "project_type",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
    )

    # Create project_status table
    op.create_table(
        "project_status",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
    )

    # Create process_step table
    op.create_table(
        "process_step",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("process_step_index", sa.Integer(), nullable=True),
        sa.Column("project_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_type_id"],
            ["project_type.id"],
        ),
    )

    # Create project table
    op.create_table(
        "project",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Details
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("project_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("internal_project_number", sa.String(), nullable=True),
        # Antragsstellenden Details
        sa.Column("salutation", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("street", sa.String(), nullable=True),
        sa.Column("house_number", sa.String(), nullable=True),
        sa.Column("address_supplement", sa.String(), nullable=True),
        sa.Column("plz", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("fax", sa.String(), nullable=True),
        # Metadata
        sa.Column("status_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "current_process_step_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["project_type_id"],
            ["project_type.id"],
        ),
        sa.ForeignKeyConstraint(
            ["status_id"],
            ["project_status.id"],
        ),
        sa.ForeignKeyConstraint(
            ["current_process_step_id"],
            ["process_step.id"],
        ),
    )

    # Create deadline table
    op.create_table(
        "deadline",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_at", sa.Date(), nullable=True),
        sa.Column("end_at", sa.Date(), nullable=True),
        sa.Column("deadline_type", sa.String(), nullable=True),
        sa.Column("legal_basis", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
    )

    # Create comment table
    op.create_table(
        "comment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("process_step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("header", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.ForeignKeyConstraint(
            ["process_step_id"],
            ["process_step.id"],
        ),
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("comment")
    op.drop_table("deadline")
    op.drop_table("project")
    op.drop_table("process_step")
    op.drop_table("project_status")
    op.drop_table("project_type")
