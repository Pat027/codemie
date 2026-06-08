"""add_updated_by_uploaded_files_to_index_info

Revision ID: 22bf0f3ba27b
Revises: k5l6m7n8o9p0
Create Date: 2026-05-29 14:08:36.939497

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

from alembic_postgresql_enum import TableReference
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '22bf0f3ba27b'
down_revision: Union[str, None] = 'k5l6m7n8o9p0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'index_info',
        sa.Column(
            'uploaded_files',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'index_info',
        sa.Column(
            'updated_by',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('index_info', 'uploaded_files')
    op.drop_column('index_info', 'updated_by')
