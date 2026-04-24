"""add_project_budget_tables

Revision ID: a1b2c3d4e5f7
Revises: 234f8f339638
Create Date: 2026-04-19 12:00:00.000000

Migration covering EPMCDME-11836:
  1. Extend budgets with budget_type and provider_metadata.
     Existing rows are backfilled to budget_type = 'global'.
  2. Create project_budget_assignments table.
  3. Create project_member_budget_assignments table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "234f8f339638"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Extend budgets table
    # ------------------------------------------------------------------
    op.add_column(
        "budgets",
        sa.Column(
            "budget_type",
            sa.VARCHAR(16),
            nullable=False,
            server_default="global",
        ),
    )
    op.add_column(
        "budgets",
        sa.Column("provider_metadata", JSONB, nullable=True),
    )

    # Backfill: all existing rows are global budgets
    op.execute("UPDATE budgets SET budget_type = 'global' WHERE budget_type IS NULL OR budget_type = ''")
    op.execute(
        """
        UPDATE budgets
        SET provider_metadata = COALESCE(provider_metadata, '{}'::jsonb) || jsonb_build_object(
            'provider', 'litellm',
            'provider_budget_ref', budget_id,
            'sync_status', 'ok'
        )
        WHERE budget_type = 'global'
          AND (
              provider_metadata IS NULL
              OR NOT (provider_metadata ? 'provider_budget_ref')
          )
        """
    )

    op.create_index("ix_budgets_budget_type", "budgets", ["budget_type"])
    op.create_index("ix_budgets_type_category", "budgets", ["budget_type", "budget_category"])

    # ------------------------------------------------------------------
    # 2. project_budget_assignments
    # One active (project_name, budget_category) pair enforced by partial unique index.
    # ------------------------------------------------------------------
    op.create_table(
        "project_budget_assignments",
        sa.Column("id", sa.VARCHAR(36), nullable=False),
        sa.Column("project_name", sa.VARCHAR(100), nullable=False),
        sa.Column("budget_category", sa.VARCHAR(32), nullable=False),
        sa.Column("budget_id", sa.VARCHAR(128), nullable=False),
        sa.Column("allocation_mode", sa.VARCHAR(16), nullable=False, server_default="equal"),
        sa.Column("assigned_by", sa.VARCHAR(255), nullable=False),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.budget_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_name"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pba_budget_id", "project_budget_assignments", ["budget_id"])
    op.create_index("ix_pba_project_name", "project_budget_assignments", ["project_name"])
    op.create_index("ix_pba_project_category", "project_budget_assignments", ["project_name", "budget_category"])
    # Partial unique: only one active assignment per (project_name, budget_category)
    op.create_index(
        "uix_pba_project_category_active",
        "project_budget_assignments",
        ["project_name", "budget_category"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------
    # 3. project_member_budget_assignments
    # Partial unique: one active member allocation per (project_name, budget_category, user_id).
    # ------------------------------------------------------------------
    op.create_table(
        "project_member_budget_assignments",
        sa.Column("id", sa.VARCHAR(36), nullable=False),
        sa.Column("project_name", sa.VARCHAR(100), nullable=False),
        sa.Column("budget_category", sa.VARCHAR(32), nullable=False),
        sa.Column("project_budget_id", sa.VARCHAR(128), nullable=False),
        sa.Column("user_id", sa.VARCHAR(36), nullable=False),
        sa.Column("allocation_mode", sa.VARCHAR(16), nullable=False, server_default="equal"),
        sa.Column("allocation_weight", sa.Float(), nullable=True),
        sa.Column("allocated_soft_budget", sa.Float(), nullable=False),
        sa.Column("allocated_max_budget", sa.Float(), nullable=False),
        sa.Column("pmba_provider_metadata", JSONB, nullable=True),
        sa.Column("spend", sa.Float(), nullable=True),
        sa.Column("budget_reset_at", sa.VARCHAR(64), nullable=True),
        sa.Column("pmba_last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("sync_status", sa.VARCHAR(32), nullable=True),
        sa.Column("override_reason", sa.VARCHAR(500), nullable=True),
        sa.Column("assigned_by", sa.VARCHAR(255), nullable=True),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("pmba_deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_budget_id"], ["budgets.budget_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_name"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pmba_project_budget_id", "project_member_budget_assignments", ["project_budget_id"])
    op.create_index("ix_pmba_user_id", "project_member_budget_assignments", ["user_id"])
    op.create_index(
        "ix_pmba_project_category",
        "project_member_budget_assignments",
        ["project_name", "budget_category"],
    )
    # Partial unique: one active allocation per member per project/category
    op.create_index(
        "uix_pmba_project_category_user_active",
        "project_member_budget_assignments",
        ["project_name", "budget_category", "user_id"],
        unique=True,
        postgresql_where=sa.text("pmba_deleted_at IS NULL"),
    )


def downgrade() -> None:
    # project_member_budget_assignments
    op.drop_index("uix_pmba_project_category_user_active", "project_member_budget_assignments")
    op.drop_index("ix_pmba_project_category", "project_member_budget_assignments")
    op.drop_index("ix_pmba_user_id", "project_member_budget_assignments")
    op.drop_index("ix_pmba_project_budget_id", "project_member_budget_assignments")
    op.drop_table("project_member_budget_assignments")

    # project_budget_assignments
    op.drop_index("uix_pba_project_category_active", "project_budget_assignments")
    op.drop_index("ix_pba_project_category", "project_budget_assignments")
    op.drop_index("ix_pba_project_name", "project_budget_assignments")
    op.drop_index("ix_pba_budget_id", "project_budget_assignments")
    op.drop_table("project_budget_assignments")

    # budgets extensions
    op.drop_index("ix_budgets_type_category", "budgets")
    op.drop_index("ix_budgets_budget_type", "budgets")
    op.drop_column("budgets", "provider_metadata")
    op.drop_column("budgets", "budget_type")
