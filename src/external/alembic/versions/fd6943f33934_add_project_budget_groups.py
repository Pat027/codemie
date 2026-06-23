"""add project_budget_groups table and backfill legacy projects

Creates project_budget_groups table with group_id column in assignments.
For legacy projects with active budget assignments but no group, creates a
group record derived from existing categories and links them via group_id.

Revision ID: fd6943f33934
Revises: p0q1r2s3t4u5
Create Date: 2026-06-22 15:35:03.558554

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import TIMESTAMP

# revision identifiers, used by Alembic.
revision: str = 'fd6943f33934'
down_revision: Union[str, None] = 'p0q1r2s3t4u5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create project_budget_groups table, add group_id, and backfill legacy projects."""
    # Step 1: Create project_budget_groups table
    op.create_table(
        "project_budget_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_name", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("budget_duration", sa.String(length=16), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_name"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pbg_project_name", "project_budget_groups", ["project_name"])
    op.create_index(
        "uix_pbg_project_active",
        "project_budget_groups",
        ["project_name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Step 2: Add group_id column to project_budget_assignments
    op.add_column(
        "project_budget_assignments",
        sa.Column("group_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_pba_group_id",
        "project_budget_assignments",
        "project_budget_groups",
        ["group_id"],
        ["id"],
    )
    op.create_index("ix_pba_group_id", "project_budget_assignments", ["group_id"])

    # Step 3: Backfill legacy projects with active budget assignments but no group
    conn = op.get_bind()
    conn.execute(
        text("""
            WITH legacy AS (
                SELECT
                    pba.project_name,
                    MIN(b.budget_duration) AS budget_duration
                FROM project_budget_assignments pba
                JOIN budgets b ON b.budget_id = pba.budget_id
                WHERE b.deleted_at IS NULL
                  AND pba.group_id IS NULL
                  AND pba.deleted_at IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM project_budget_groups pbg
                      WHERE pbg.project_name = pba.project_name
                        AND pbg.deleted_at IS NULL
                  )
                GROUP BY pba.project_name
            ),
            inserted AS (
                INSERT INTO project_budget_groups
                    (id, project_name, name, budget_duration, created_by, created_at)
                SELECT
                    gen_random_uuid()::text,
                    project_name,
                    project_name,
                    budget_duration,
                    'migration',
                    now()
                FROM legacy
                RETURNING id, project_name
            )
            UPDATE project_budget_assignments
            SET group_id = inserted.id
            FROM inserted
            WHERE project_budget_assignments.project_name = inserted.project_name
              AND project_budget_assignments.group_id IS NULL
              AND project_budget_assignments.deleted_at IS NULL
        """)
    )


def downgrade() -> None:
    """Unlink ALL assignments, delete ALL groups, drop group_id, and drop project_budget_groups table."""
    conn = op.get_bind()

    # Step 1: Unlink ALL assignments before dropping the table
    conn.execute(
        text("""
            UPDATE project_budget_assignments
            SET group_id = NULL
            WHERE group_id IS NOT NULL
        """)
    )

    # Step 2: Delete ALL groups (migration-created + API-created)
    conn.execute(
        text("""
            DELETE FROM project_budget_groups
        """)
    )

    # Step 3: Remove group_id column and its foreign key from project_budget_assignments
    op.drop_index("ix_pba_group_id", table_name="project_budget_assignments")
    op.drop_constraint("fk_pba_group_id", "project_budget_assignments", type_="foreignkey")
    op.drop_column("project_budget_assignments", "group_id")

    # Step 4: Drop project_budget_groups table and its indexes
    op.drop_index("uix_pbg_project_active", table_name="project_budget_groups")
    op.drop_index("ix_pbg_project_name", table_name="project_budget_groups")
    op.drop_table("project_budget_groups")
