"""rename document.document_type_id to ai_suggested_required_document_type_id

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-19 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename document_type_id to ai_suggested_required_document_type_id."""
    op.execute(
        "ALTER TABLE document RENAME COLUMN document_type_id TO ai_suggested_required_document_type_id"
    )


def downgrade() -> None:
    """Rename ai_suggested_required_document_type_id back to document_type_id."""
    op.execute(
        "ALTER TABLE document RENAME COLUMN ai_suggested_required_document_type_id TO document_type_id"
    )
