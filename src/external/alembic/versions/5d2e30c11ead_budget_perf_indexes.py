"""budget_perf_indexes

Revision ID: 5d2e30c11ead
Revises: e5f6a7b8c9d1
Create Date: 2026-04-21 20:32:02.625060

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5d2e30c11ead'
down_revision: Union[str, None] = 'e5f6a7b8c9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial indexes for active project budget assignment queries."""
    # Partial index: active project assignments by (project_name, budget_category)
    op.create_index(
        "idx_pba_active_project_category",
        "project_budget_assignments",
        ["project_name", "budget_category"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Partial index: active member allocations by (project_name, budget_category, user_id)
    op.create_index(
        "idx_pmba_active_project_category_user",
        "project_member_budget_assignments",
        ["project_name", "budget_category", "user_id"],
        postgresql_where=sa.text("pmba_deleted_at IS NULL"),
    )

    # Composite index: user budget assignments by (user_id, category)
    # May already exist — if_not_exists prevents duplicate index errors.
    op.create_index(
        "idx_uba_user_category",
        "user_budget_assignments",
        ["user_id", "category"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Remove budget performance indexes."""
    op.drop_index("idx_uba_user_category", table_name="user_budget_assignments", if_exists=True)
    op.drop_index("idx_pmba_active_project_category_user", table_name="project_member_budget_assignments")
    op.drop_index("idx_pba_active_project_category", table_name="project_budget_assignments")
