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

"""Add display_name column to applications table

Revision ID: p1q2r3s4t5u6
Revises: r2s3t4u5v6w7
Create Date: 2026-06-08 00:00:00.000000

Adds an optional human-friendly display_name field to the applications table.
Existing rows get NULL (UI falls back to the technical name field).
"""

from alembic import op
import sqlalchemy as sa

revision = "p1q2r3s4t5u6"
down_revision = "r2s3t4u5v6w7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("applications", sa.Column("display_name", sa.String(150), nullable=True))


def downgrade():
    op.drop_column("applications", "display_name")
