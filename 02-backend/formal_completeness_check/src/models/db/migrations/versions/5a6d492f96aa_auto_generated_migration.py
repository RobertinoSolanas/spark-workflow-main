"""auto-generated migration

Revision ID: 5a6d492f96aa
Revises: 2fb6d5cff5ba
Create Date: 2026-02-17 15:17:44.855743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a6d492f96aa'
down_revision: Union[str, Sequence[str], None] = '2fb6d5cff5ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - skipped, changes already applied by a1b2c3d4e5f6."""
    pass


def downgrade() -> None:
    """Downgrade schema - skipped, handled by a1b2c3d4e5f6."""
    pass