"""Add length constraint and not null to project_type.name

Revision ID: 004_pt_name_length
Revises: 003_uq_project_type_name
Create Date: 2026-03-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_pt_name_length"
down_revision: str | Sequence[str] | None = "003_uq_project_type_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "project_type",
        "name",
        existing_type=sa.String(),
        type_=sa.String(length=255),
        existing_nullable=True,
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "project_type",
        "name",
        existing_type=sa.String(length=255),
        type_=sa.String(),
        existing_nullable=False,
        nullable=True,
    )
