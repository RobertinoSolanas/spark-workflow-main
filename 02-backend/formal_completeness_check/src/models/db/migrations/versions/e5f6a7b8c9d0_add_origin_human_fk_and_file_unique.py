"""add document_type.origin, document human FK, and (project_id, file_id) unique index

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-19 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fix 3: add origin column to document_type, backfill from category name, make NOT NULL
    op.add_column("document_type", sa.Column("origin", sa.String(), nullable=True))
    op.execute("""
        UPDATE document_type
        SET origin = CASE
            WHEN category_id IN (
                SELECT id FROM category WHERE name = 'Benutzerdefiniert'
            ) THEN 'custom'
            ELSE 'system'
        END
    """)
    op.alter_column("document_type", "origin", nullable=False)

    # Fix 2: partial unique index on document(project_id, file_id) where file_id IS NOT NULL
    op.execute(
        "CREATE UNIQUE INDEX uq_document_project_file_id "
        "ON document(project_id, file_id) WHERE file_id IS NOT NULL"
    )

    # Fix 1: single-column FK human_required_document_type_id → document_type.id with SET NULL
    # (single-column avoids nullifying project_id which is NOT NULL)
    op.create_foreign_key(
        "fk_document_human_required_document_type",
        "document",
        "document_type",
        ["human_required_document_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Fix 4: CHECK constraint so only valid origin values can be stored
    op.create_check_constraint(
        "chk_document_type_origin",
        "document_type",
        "origin IN ('system', 'custom')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_document_type_origin", "document_type", type_="check")
    op.drop_constraint(
        "fk_document_human_required_document_type", "document", type_="foreignkey"
    )
    op.drop_index("uq_document_project_file_id", table_name="document")
    op.drop_column("document_type", "origin")
