"""project_member_budget_spend_rows

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f7
Create Date: 2026-04-20 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("project_spend_tracking", sa.Column("user_id", sa.VARCHAR(), nullable=True))
    op.add_column("project_spend_tracking", sa.Column("provider_subject_id", sa.VARCHAR(), nullable=True))

    op.drop_constraint(
        "ck_project_spend_tracking_subject_type_values",
        "project_spend_tracking",
        type_="check",
    )
    op.create_check_constraint(
        "ck_project_spend_tracking_subject_type_values",
        "project_spend_tracking",
        "spend_subject_type IN ('key', 'budget', 'project_budget', 'member_budget')",
    )

    op.create_index(
        "uix_project_spend_tracking_project_budget_rows",
        "project_spend_tracking",
        ["project_name", "budget_id", "spend_date"],
        unique=True,
        postgresql_where=sa.text("spend_subject_type = 'project_budget'"),
    )
    op.create_index(
        "uix_project_spend_tracking_member_budget_rows",
        "project_spend_tracking",
        ["project_name", "budget_id", "user_id", "spend_date"],
        unique=True,
        postgresql_where=sa.text("spend_subject_type = 'member_budget'"),
    )


def downgrade() -> None:
    op.drop_index("uix_project_spend_tracking_member_budget_rows", table_name="project_spend_tracking")
    op.drop_index("uix_project_spend_tracking_project_budget_rows", table_name="project_spend_tracking")
    op.drop_constraint(
        "ck_project_spend_tracking_subject_type_values",
        "project_spend_tracking",
        type_="check",
    )
    op.create_check_constraint(
        "ck_project_spend_tracking_subject_type_values",
        "project_spend_tracking",
        "spend_subject_type IN ('key', 'budget')",
    )
    op.drop_column("project_spend_tracking", "provider_subject_id")
    op.drop_column("project_spend_tracking", "user_id")
