"""add versioning and resolved columns

Revision ID: a1b2c3d4e5f6
Revises: 2fb6d5cff5ba
Create Date: 2026-02-17 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "2fb6d5cff5ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # New tables
    op.create_table(
        "project_template_version",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", name="uq_project_template_version_project_id"
        ),
    )
    op.create_index(
        op.f("ix_project_template_version_project_id"),
        "project_template_version",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "table_of_content_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "is_resolved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_table_of_content_notes_project_id"),
        "table_of_content_notes",
        ["project_id"],
        unique=False,
    )

    # New NOT NULL columns on existing tables — server_default ensures existing rows get a value
    op.add_column(
        "document",
        sa.Column(
            "is_resolved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "document_type",
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "template_category",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "template_document_type",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    # Update unique constraints on template tables
    op.drop_constraint("uq_template_category_name", "template_category", type_="unique")
    op.create_unique_constraint(
        "uq_template_category_name_version", "template_category", ["name", "version"]
    )

    op.drop_constraint(
        "uq_template_document_type_name", "template_document_type", type_="unique"
    )
    op.create_unique_constraint(
        "uq_template_document_type_name_version",
        "template_document_type",
        ["name", "version"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Restore old unique constraints
    op.drop_constraint(
        "uq_template_document_type_name_version",
        "template_document_type",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_template_document_type_name", "template_document_type", ["name"]
    )

    op.drop_constraint(
        "uq_template_category_name_version", "template_category", type_="unique"
    )
    op.create_unique_constraint(
        "uq_template_category_name", "template_category", ["name"]
    )

    # Drop added columns
    op.drop_column("template_document_type", "version")
    op.drop_column("template_category", "version")
    op.drop_column("document_type", "deleted")
    op.drop_column("document", "is_resolved")

    # Drop new tables
    op.drop_index(
        op.f("ix_table_of_content_notes_project_id"),
        table_name="table_of_content_notes",
    )
    op.drop_table("table_of_content_notes")
    op.drop_index(
        op.f("ix_project_template_version_project_id"),
        table_name="project_template_version",
    )
    op.drop_table("project_template_version")
