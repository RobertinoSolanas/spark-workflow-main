"""Add deleted column to template_category and template_document_type tables.

Revision ID: a1b2c3d4e5f7
Revises: bbb28e9b9fda
Create Date: 2026-03-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: str = "bbb28e9b9fda"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add deleted column to template_category
    op.add_column(
        "template_category",
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Add deleted column to template_document_type
    op.add_column(
        "template_document_type",
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Replace plain unique constraints with partial unique indexes
    # (so soft-deleted records don't block re-creation with the same name)
    op.drop_constraint("uq_template_category_name_version", "template_category", type_="unique")
    op.create_index(
        "uq_template_category_project_type_name",
        "template_category",
        ["project_type_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted IS NOT TRUE"),
        sqlite_where=sa.text("deleted IS NOT TRUE"),
    )

    op.drop_constraint(
        "uq_template_document_type_name_version",
        "template_document_type",
        type_="unique",
    )
    op.create_index(
        "uq_template_document_type_category_name",
        "template_document_type",
        ["template_category_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted IS NOT TRUE"),
        sqlite_where=sa.text("deleted IS NOT TRUE"),
    )

    op.drop_column("template_document_type", "version")
    op.drop_column("template_category", "version")


def downgrade() -> None:
    # Reverse: drop partial indexes, recreate plain unique constraints
    # Soft-delete rows can duplicate active names; remove them before restoring
    # non-partial unique constraints from the previous revision.
    op.add_column(
        "template_category",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "template_document_type",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    op.execute(sa.text("DELETE FROM template_document_type WHERE deleted IS TRUE"))
    op.execute(sa.text("DELETE FROM template_category WHERE deleted IS TRUE"))

    op.drop_index(
        "uq_template_document_type_category_name",
        table_name="template_document_type",
    )
    op.create_unique_constraint(
        "uq_template_document_type_name_version",
        "template_document_type",
        ["name", "version"],
    )

    op.drop_index(
        "uq_template_category_project_type_name",
        table_name="template_category",
    )
    op.create_unique_constraint(
        "uq_template_category_name_version",
        "template_category",
        ["name", "version"],
    )

    op.drop_column("template_document_type", "deleted")
    op.drop_column("template_category", "deleted")
