"""add_deleted_at_to_budgets

Revision ID: d4e5f6a7b8ca
Revises: c2d3e4f5a6b7
Create Date: 2026-04-20 12:00:00.000000

Allow re-creation of deleted project budgets by soft-deleting Budget rows.

Changes:
  1. Add deleted_at column to budgets.
  2. Drop the hard unique constraint on name (uix_budgets_name).
  3. Add a partial unique index on name WHERE deleted_at IS NULL,
     so name uniqueness is enforced only among active budgets.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8ca"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "budgets",
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Replace the hard unique constraint with a partial unique index so that
    # deleted budgets do not block re-use of the same name.
    op.drop_constraint("uix_budgets_name", "budgets", type_="unique")
    op.create_index(
        "uix_budgets_name_active",
        "budgets",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uix_budgets_name_active", table_name="budgets")
    op.create_unique_constraint("uix_budgets_name", "budgets", ["name"])
    op.drop_column("budgets", "deleted_at")
