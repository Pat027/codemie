"""add_lifecycle_state_to_index_info

Revision ID: f9g0h1i2j3k4
Revises: 22bf0f3ba27b
Create Date: 2026-04-15 10:58:48.000000

Adds lifecycle_state and marked_stale_at fields to index_info table for tracking datasource lifecycle.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f9g0h1i2j3k4"
down_revision: Union[str, None] = "k6l7m8n9o0p1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add lifecycle_state and marked_stale_at columns to index_info table."""
    # Create PostgreSQL enum type for lifecycle_state
    # Uses UPPERCASE values to match SQLAlchemy enum member names
    lifecycle_state_enum = postgresql.ENUM(
        "ACTIVE",
        "STALE",
        "ARCHIVED",
        name="lifecyclestate",
        create_type=True,
    )
    lifecycle_state_enum.create(op.get_bind(), checkfirst=True)

    # Add lifecycle_state column with default 'ACTIVE'
    op.add_column(
        "index_info",
        sa.Column(
            "lifecycle_state",
            postgresql.ENUM(
                "ACTIVE",
                "STALE",
                "ARCHIVED",
                name="lifecyclestate",
                create_type=False,
            ),
            nullable=False,
            server_default="ACTIVE",
        ),
    )

    # Add marked_stale_at column (nullable datetime without timezone - UTC assumed)
    op.add_column(
        "index_info",
        sa.Column(
            "marked_stale_at",
            sa.TIMESTAMP(timezone=False),
            nullable=True,
        ),
    )

    # Create index for efficient queries by lifecycle state
    op.create_index(
        "ix_index_info_lifecycle_state",
        "index_info",
        ["lifecycle_state"],
    )

    # Create index for efficient time-based queries on marked_stale_at
    op.create_index(
        "ix_index_info_marked_stale_at",
        "index_info",
        ["marked_stale_at"],
    )


def downgrade() -> None:
    """Remove lifecycle_state and marked_stale_at columns from index_info table."""
    # Drop indexes first
    op.drop_index("ix_index_info_marked_stale_at", "index_info")
    op.drop_index("ix_index_info_lifecycle_state", "index_info")

    # Drop columns
    op.drop_column("index_info", "marked_stale_at")
    op.drop_column("index_info", "lifecycle_state")

    # Drop the PostgreSQL enum type
    postgresql.ENUM(
        "ACTIVE",
        "STALE",
        "ARCHIVED",
        name="lifecyclestate",
    ).drop(op.get_bind(), checkfirst=True)
