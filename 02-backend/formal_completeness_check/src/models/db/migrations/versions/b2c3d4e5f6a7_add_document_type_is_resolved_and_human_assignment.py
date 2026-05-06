"""add document_type is_resolved and document human_required_document_type_id

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-19 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "document_type",
        sa.Column(
            "is_resolved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "document",
        sa.Column("human_required_document_type_id", sa.UUID(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document", "human_required_document_type_id")
    op.drop_column("document_type", "is_resolved")
