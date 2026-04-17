"""Add source_ref columns and convert process_step to enum

Revision ID: a3f9d2c1b4e7
Revises: 025c81cd95ae
Create Date: 2026-03-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3f9d2c1b4e7"
down_revision: str | Sequence[str] | None = "025c81cd95ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

commentprocessstep = postgresql.ENUM(
    "unsorted",
    "formalCompletenessCheck",
    "plausibilityCheck",
    "materialCompletenessCheck",
    "legalReview",
    name="commentprocessstep",
)

commentsourcetype = postgresql.ENUM(
    "tableOfContents",
    "requiredDocuments",
    "contradiction",
    "materialLaw",
    "materialNorm",
    "materialSatz",
    "materialFundstelle",
    "manual",
    name="commentsourcetype",
)


def upgrade() -> None:
    """Upgrade schema."""
    commentprocessstep.create(op.get_bind(), checkfirst=True)
    commentsourcetype.create(op.get_bind(), checkfirst=True)

    op.alter_column(
        "comment",
        "process_step",
        existing_type=sa.String(),
        type_=commentprocessstep,
        postgresql_using="process_step::commentprocessstep",
        nullable=False,
    )

    op.add_column(
        "comment",
        sa.Column("source_type", commentsourcetype, nullable=True),
    )
    op.add_column(
        "comment",
        sa.Column("source_item_id", sa.String(255), nullable=True),
    )

    op.create_index(
        "ix_comment_project_id", "comment", ["project_id"], if_not_exists=True
    )
    op.create_index(
        "ix_comment_project_process_step",
        "comment",
        ["project_id", "process_step"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_comment_project_process_step", table_name="comment")
    op.drop_index("ix_comment_project_id", table_name="comment")

    op.drop_column("comment", "source_item_id")
    op.drop_column("comment", "source_type")

    op.alter_column(
        "comment",
        "process_step",
        existing_type=commentprocessstep,
        type_=sa.String(),
        postgresql_using="process_step::text",
        nullable=False,
    )

    commentsourcetype.drop(op.get_bind(), checkfirst=True)
    commentprocessstep.drop(op.get_bind(), checkfirst=True)
