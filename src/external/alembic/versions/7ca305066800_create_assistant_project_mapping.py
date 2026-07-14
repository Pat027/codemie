"""create assistant_project_mapping

Revision ID: 7ca305066800
Revises: r2s3t4u5v6w7
Create Date: 2026-07-08 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "7ca305066800"
down_revision: Union[str, None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_project_mapping",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("assistant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("feature", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assistant_id"],
            ["assistants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assistant_id", "project_name", "feature", name="uix_assistant_project_mapping"),
    )
    op.create_index(
        op.f("ix_assistant_project_mapping_project_name"),
        "assistant_project_mapping",
        ["project_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_assistant_project_mapping_project_name"), table_name="assistant_project_mapping")
    op.drop_table("assistant_project_mapping")
