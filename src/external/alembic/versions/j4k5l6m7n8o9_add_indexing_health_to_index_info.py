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

"""add last_reindex_triggered_at to index_info

Revision ID: j4k5l6m7n8o9
Revises: f9e8d7c6b5a4
Create Date: 2026-05-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, Sequence[str], None] = "f9e8d7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("index_info", sa.Column("last_reindex_triggered_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("index_info", "last_reindex_triggered_at")
