"""Add ZIP to filetypeenum

Revision ID: 4a3428c85459
Revises: 91a177d23921
Create Date: 2026-02-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "4a3428c85459"
down_revision: str | Sequence[str] | None = "91a177d23921"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE filetypeenum ADD VALUE IF NOT EXISTS 'ZIP'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The value will remain but is harmless if unused.
    pass
