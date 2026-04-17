"""Add workflow status to zip_file

Revision ID: c2f0f8907dd1
Revises: 4a3428c85459
Create Date: 2026-02-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2f0f8907dd1"
down_revision: str | Sequence[str] | None = "4a3428c85459"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKFLOW_STATUS_ENUM_NAME = "workflowstatusenum"


def upgrade() -> None:
    workflow_status_enum = sa.Enum(
        "PENDING",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "CANCELED",
        "TERMINATED",
        "CONTINUED_AS_NEW",
        "TIMED_OUT",
        name=WORKFLOW_STATUS_ENUM_NAME,
    )
    workflow_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "zip_file",
        sa.Column(
            "workflow_status",
            workflow_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.create_index(
        op.f("ix_zip_file_workflow_status"),
        "zip_file",
        ["workflow_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_zip_file_workflow_status"), table_name="zip_file")
    op.drop_column("zip_file", "workflow_status")

    workflow_status_enum = sa.Enum(name=WORKFLOW_STATUS_ENUM_NAME)
    workflow_status_enum.drop(op.get_bind(), checkfirst=True)
