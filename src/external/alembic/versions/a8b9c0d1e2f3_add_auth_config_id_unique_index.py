# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""add auth_config_id unique index on mcp_configs

Revision ID: a8b9c0d1e2f3
Revises: a9c8d7e6f5b4
Create Date: 2026-04-13 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "a9c8d7e6f5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial unique expression index on auth_config.id within config JSONB column.

    The index uses ``(config->'auth_config'->>'id')`` with an ``IS NOT NULL`` predicate
    so rows without ``auth_config`` are excluded from the uniqueness constraint (AC #4).
    """
    op.create_index(
        "ix_mcp_configs_auth_config_id",
        "mcp_configs",
        [sa.literal_column("((config->'auth_config'->>'id'))")],
        unique=True,
        postgresql_using="btree",
        postgresql_where=sa.text("(config->'auth_config'->>'id') IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove the auth_config_id unique expression index."""
    op.drop_index("ix_mcp_configs_auth_config_id", table_name="mcp_configs")
