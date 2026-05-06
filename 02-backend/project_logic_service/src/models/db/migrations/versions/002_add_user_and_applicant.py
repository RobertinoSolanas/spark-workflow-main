"""Add user and applicant tables, update project foreign keys

Revision ID: 002_add_user_and_applicant
Revises: 001_initial_schema
Create Date: 2024-01-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_add_user_and_applicant"
down_revision: str | Sequence[str] | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create user table
    op.create_table(
        "user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("keycloak_user_id", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_keycloak_user_id", "user", ["keycloak_user_id"], unique=True
    )

    # Create applicant table
    op.create_table(
        "applicant",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("salutation", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("street", sa.String(), nullable=True),
        sa.Column("house_number", sa.String(), nullable=True),
        sa.Column("address_supplement", sa.String(), nullable=True),
        sa.Column("plz", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("fax", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add applicant_id to project table
    op.add_column(
        "project",
        sa.Column("applicant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_project_applicant_id",
        "project",
        "applicant",
        ["applicant_id"],
        ["id"],
    )

    # Update project.created_by_id to have foreign key constraint
    op.create_foreign_key(
        "fk_project_created_by_id",
        "project",
        "user",
        ["created_by_id"],
        ["id"],
    )

    # Update comment.user_id to have foreign key constraint
    op.create_foreign_key(
        "fk_comment_user_id",
        "comment",
        "user",
        ["user_id"],
        ["id"],
    )

    # Remove applicant columns from project table
    op.drop_column("project", "salutation")
    op.drop_column("project", "company")
    op.drop_column("project", "first_name")
    op.drop_column("project", "last_name")
    op.drop_column("project", "street")
    op.drop_column("project", "house_number")
    op.drop_column("project", "address_supplement")
    op.drop_column("project", "plz")
    op.drop_column("project", "location")
    op.drop_column("project", "country")
    op.drop_column("project", "email")
    op.drop_column("project", "phone")
    op.drop_column("project", "fax")


def downgrade() -> None:
    # Add applicant columns back to project table
    op.add_column("project", sa.Column("salutation", sa.String(), nullable=True))
    op.add_column("project", sa.Column("company", sa.String(), nullable=True))
    op.add_column("project", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("project", sa.Column("last_name", sa.String(), nullable=True))
    op.add_column("project", sa.Column("street", sa.String(), nullable=True))
    op.add_column("project", sa.Column("house_number", sa.String(), nullable=True))
    op.add_column(
        "project", sa.Column("address_supplement", sa.String(), nullable=True)
    )
    op.add_column("project", sa.Column("plz", sa.String(), nullable=True))
    op.add_column("project", sa.Column("location", sa.String(), nullable=True))
    op.add_column("project", sa.Column("country", sa.String(), nullable=True))
    op.add_column("project", sa.Column("email", sa.String(), nullable=True))
    op.add_column("project", sa.Column("phone", sa.String(), nullable=True))
    op.add_column("project", sa.Column("fax", sa.String(), nullable=True))

    # Drop foreign key constraints
    op.drop_constraint("fk_comment_user_id", "comment", type_="foreignkey")
    op.drop_constraint("fk_project_created_by_id", "project", type_="foreignkey")
    op.drop_constraint("fk_project_applicant_id", "project", type_="foreignkey")

    # Remove applicant_id from project table
    op.drop_column("project", "applicant_id")

    # Drop applicant table
    op.drop_table("applicant")

    # Drop user table
    op.drop_index("ix_user_keycloak_user_id", table_name="user")
    op.drop_table("user")
