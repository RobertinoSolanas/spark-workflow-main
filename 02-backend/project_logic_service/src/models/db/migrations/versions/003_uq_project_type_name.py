"""add unique constraint to project_type.name

Revision ID: 003_uq_project_type_name
Revises: c0d72ef5d87c
Create Date: 2026-03-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_uq_project_type_name"
down_revision: str | Sequence[str] | None = "c0d72ef5d87c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Remove rows with NULL names — invalid data that would block the NOT NULL constraint in 004.
    op.execute(sa.text("DELETE FROM project_type WHERE name IS NULL"))

    # Remove duplicate names, keeping the row with the smallest id for each name.
    op.execute(
        sa.text(
            """
            DELETE FROM project_type
            WHERE id NOT IN (
                SELECT MIN(id::text)::uuid
                FROM project_type
                GROUP BY name
            )
            """
        )
    )
    op.create_unique_constraint(
        "uq_project_type_name", "project_type", ["name"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_project_type_name", "project_type", type_="unique")
