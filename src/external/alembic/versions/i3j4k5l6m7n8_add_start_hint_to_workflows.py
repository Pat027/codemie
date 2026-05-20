"""add start_hint to workflows

Revision ID: i3j4k5l6m7n8
Revises: c5d6e7f8a9b0
Create Date: 2026-04-24 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add start_hint column to workflows table."""
    op.add_column("workflows", sa.Column("start_hint", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove start_hint column from workflows table."""
    op.drop_column("workflows", "start_hint")
