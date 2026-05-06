"""remove fact_text column

Revision ID: 9000d8aa34dc
Revises: 85bd27a6db27
Create Date: 2026-01-05 17:47:30.259744

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9000d8aa34dc"
down_revision: str | Sequence[str] | None = "85bd27a6db27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove fact_text column from plausibility_note table."""
    op.drop_column("plausibility_note", "fact_text")


def downgrade() -> None:
    """Restore fact_text column to plausibility_note table."""
    op.add_column(
        "plausibility_note",
        sa.Column("fact_text", sa.Text(), nullable=False, server_default=""),
    )
