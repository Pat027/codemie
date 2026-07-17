"""create_activity_events_table

Revision ID: 38255069bfab
Revises: 7ca305066800
Create Date: 2026-07-15 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "38255069bfab"
down_revision: Union[str, None] = "7ca305066800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create activity_events — append-only audit log, domain-extensible via discriminator."""
    op.create_table(
        "activity_events",
        sa.Column("id", sa.VARCHAR(36), nullable=False),
        sa.Column("domain", sa.VARCHAR(64), nullable=False),
        sa.Column("event_type", sa.VARCHAR(128), nullable=False),
        sa.Column("entity_type", sa.VARCHAR(64), nullable=True),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column(
            "actor_id",
            sa.VARCHAR(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_activity_events_entity_type_entity_id"),
        "activity_events",
        ["entity_type", "entity_id"],
        postgresql_where=sa.text("entity_id IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_activity_events_actor_id_created_at"),
        "activity_events",
        ["actor_id", "created_at"],
        postgresql_where=sa.text("actor_id IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_activity_events_domain_created_at"),
        "activity_events",
        ["domain", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_activity_events_domain_created_at"), table_name="activity_events")
    op.drop_index(op.f("ix_activity_events_actor_id_created_at"), table_name="activity_events")
    op.drop_index(op.f("ix_activity_events_entity_type_entity_id"), table_name="activity_events")
    op.drop_table("activity_events")
