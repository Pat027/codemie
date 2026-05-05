"""create_skill_events_table

Revision ID: c4f2a8b6d1e9
Revises: h2b3c4d5e6f7
Create Date: 2026-05-04 22:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4f2a8b6d1e9"
down_revision: Union[str, None] = "h2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create `skill_events` — durable record of `codemie skill *` lifecycle events.

    One row per (lifecycle event, skill). Free-form TEXT for command/status/
    scope so adding new commands (e.g. `find`, `pin`, `share`) never requires
    a follow-up migration; validation lives at the API layer.
    """
    op.create_table(
        "skill_events",
        # CommonBaseModel inherited columns (id/date/update_date)
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("update_date", sa.DateTime(), nullable=True),
        # Event timestamp
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Identity / context
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "user_email",
            sqlmodel.sql.sqltypes.AutoString(length=320),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=False,
        ),
        sa.Column(
            "agent",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
            server_default="codemie-skills",
        ),
        sa.Column(
            "agent_version",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column(
            "client_type",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column(
            "cli_version",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column(
            "repository",
            sqlmodel.sql.sqltypes.AutoString(length=512),
            nullable=True,
        ),
        sa.Column(
            "branch",
            sqlmodel.sql.sqltypes.AutoString(length=256),
            nullable=True,
        ),
        sa.Column(
            "project",
            sqlmodel.sql.sqltypes.AutoString(length=256),
            nullable=True,
        ),
        # Lifecycle (free-form TEXT; API-level validation only)
        sa.Column(
            "command",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column(
            "scope",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=True,
        ),
        sa.Column(
            "error_code",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=True,
        ),
        sa.Column(
            "agent_selection_mode",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=True,
        ),
        # Per-operation list (JSONB matches ai_kata.tags / .roles convention)
        sa.Column(
            "target_agents",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Skill identity (per-row; null when wrapper can't attribute)
        sa.Column(
            "source",
            sqlmodel.sql.sqltypes.AutoString(length=512),
            nullable=True,
        ),
        sa.Column(
            "skill_slug",
            sqlmodel.sql.sqltypes.AutoString(length=256),
            nullable=True,
        ),
        sa.Column(
            "skill_id",
            sqlmodel.sql.sqltypes.AutoString(length=1024),
            nullable=True,
        ),
        # Forward-compat escape hatch (any new field can ship without migration)
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes — match SQLModel `index=True` declarations + composite indexes
    # from `__table_args__`. Keep names aligned with project convention.
    op.create_index(
        op.f("ix_skill_events_created_at"),
        "skill_events",
        ["created_at"],
    )
    op.create_index(
        op.f("ix_skill_events_user_id"),
        "skill_events",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_skill_events_session_id"),
        "skill_events",
        ["session_id"],
    )
    op.create_index(
        op.f("ix_skill_events_command"),
        "skill_events",
        ["command"],
    )
    op.create_index(
        op.f("ix_skill_events_status"),
        "skill_events",
        ["status"],
    )
    op.create_index(
        op.f("ix_skill_events_skill_slug"),
        "skill_events",
        ["skill_slug"],
    )
    op.create_index(
        op.f("ix_skill_events_skill_id"),
        "skill_events",
        ["skill_id"],
    )
    op.create_index(
        "ix_skill_events_user_created",
        "skill_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_skill_events_command_created",
        "skill_events",
        ["command", "created_at"],
    )


def downgrade() -> None:
    """Drop `skill_events` and its indexes."""
    op.drop_index("ix_skill_events_command_created", table_name="skill_events")
    op.drop_index("ix_skill_events_user_created", table_name="skill_events")
    op.drop_index(op.f("ix_skill_events_skill_id"), table_name="skill_events")
    op.drop_index(op.f("ix_skill_events_skill_slug"), table_name="skill_events")
    op.drop_index(op.f("ix_skill_events_status"), table_name="skill_events")
    op.drop_index(op.f("ix_skill_events_command"), table_name="skill_events")
    op.drop_index(op.f("ix_skill_events_session_id"), table_name="skill_events")
    op.drop_index(op.f("ix_skill_events_user_id"), table_name="skill_events")
    op.drop_index(op.f("ix_skill_events_created_at"), table_name="skill_events")
    op.drop_table("skill_events")
