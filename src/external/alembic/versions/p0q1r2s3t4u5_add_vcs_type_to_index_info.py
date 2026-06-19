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

"""Add vcs_type column to index_info; migrate legacy index_type='svn' rows

Revision ID: p0q1r2s3t4u5
Revises: q1r2s3t4u5v6
Create Date: 2026-06-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'p0q1r2s3t4u5'
down_revision: Union[str, None] = 'q1r2s3t4u5v6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col['name'] for col in inspector.get_columns('index_info')]
    if 'vcs_type' not in existing_columns:
        op.add_column('index_info', sa.Column('vcs_type', sa.String(), nullable=False, server_default='git'))
    # Fix legacy rows where index_type was stored as 'svn' directly
    op.execute("UPDATE index_info SET vcs_type = 'svn', index_type = 'code' WHERE index_type = 'svn'")
    # Fix rows created by the SVN processor (which stores index_type='code', not 'svn').
    # These can be identified by joining with svn_repositories on project_name/repo_name.
    op.execute("""
        UPDATE index_info
        SET vcs_type = 'svn'
        FROM svn_repositories
        WHERE index_info.project_name = svn_repositories.app_id
          AND index_info.repo_name = svn_repositories.name
          AND index_info.vcs_type = 'git'
    """)


def downgrade() -> None:
    op.drop_column('index_info', 'vcs_type')
