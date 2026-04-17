"""add project_type_id to template_category and project_template_version

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-02-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "template_category",
        sa.Column("project_type_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_template_category_project_type_id",
        "template_category",
        ["project_type_id"],
    )

    op.add_column(
        "project_template_version",
        sa.Column("project_type_id", PG_UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_template_version", "project_type_id")
    op.drop_index(
        "ix_template_category_project_type_id", table_name="template_category"
    )
    op.drop_column("template_category", "project_type_id")
