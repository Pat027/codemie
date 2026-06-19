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

"""Add SVN datasource: credentialtypes enum and svn_repositories table

Revision ID: q1r2s3t4u5v6
Revises: o9p0q1r2s3t4
Create Date: 2026-06-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from alembic_postgresql_enum import TableReference
from sqlalchemy.dialects import postgresql

revision: str = 'q1r2s3t4u5v6'
down_revision: Union[str, None] = 'o9p0q1r2s3t4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add SVN to credentialtypes enum and create svn_repositories table."""
    op.sync_enum_values(
        enum_schema='codemie',
        enum_name='credentialtypes',
        new_values=[
            'JIRA',
            'CONFLUENCE',
            'GIT',
            'KUBERNETES',
            'AWS',
            'GCP',
            'KEYCLOAK',
            'AZURE',
            'ELASTIC',
            'OPEN_API',
            'PLUGIN',
            'FILE_SYSTEM',
            'SCHEDULER',
            'WEBHOOK',
            'EMAIL',
            'AZURE_DEVOPS',
            'SONAR',
            'SQL',
            'TELEGRAM',
            'ZEPHYR_SCALE',
            '_ZEPHYR_CLOUD',
            'ZEPHYR_SQUAD',
            'XRAY',
            'SERVICENOW',
            'REPORT_PORTAL',
            'ENVIRONMENT_VARS',
            'AUTH_TOKEN',
            'A2A',
            'LITE_LLM',
            'DIAL',
            'SHAREPOINT',
            'SVN',
        ],
        affected_columns=[TableReference(table_schema='codemie', table_name='settings', column_name='credential_type')],
        enum_values_to_rename=[],
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'svn_repositories' not in inspector.get_table_names():
        op.create_table(
            'svn_repositories',
            sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('date', sa.DateTime(), nullable=True),
            sa.Column('update_date', sa.DateTime(), nullable=True),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('description', sa.String(), nullable=False),
            sa.Column('link', sa.String(), nullable=False),
            sa.Column('branch', sa.String(), nullable=False),
            sa.Column('files_filter', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column(
                'index_type',
                postgresql.ENUM('CODE', 'SUMMARY', 'CHUNK_SUMMARY', name='codeindextype', create_type=False),
                nullable=False,
            ),
            sa.Column('last_indexed_revision', sa.Integer(), nullable=True),
            sa.Column('embeddings_model', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('summarization_model', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('prompt', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('docs_generation', sa.Boolean(), nullable=True),
            sa.Column('project_space_visible', sa.Boolean(), nullable=False),
            sa.Column('setting_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('original_storage', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('app_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_svn_repositories_app_id'), 'svn_repositories', ['app_id'], unique=False)


def downgrade() -> None:
    """Drop svn_repositories table and remove SVN from credentialtypes enum."""
    op.drop_index(op.f('ix_svn_repositories_app_id'), table_name='svn_repositories')
    op.drop_table('svn_repositories')

    op.execute("DELETE FROM codemie.settings WHERE credential_type = 'SVN'")
    op.sync_enum_values(
        enum_schema='codemie',
        enum_name='credentialtypes',
        new_values=[
            'JIRA',
            'CONFLUENCE',
            'GIT',
            'KUBERNETES',
            'AWS',
            'GCP',
            'KEYCLOAK',
            'AZURE',
            'ELASTIC',
            'OPEN_API',
            'PLUGIN',
            'FILE_SYSTEM',
            'SCHEDULER',
            'WEBHOOK',
            'EMAIL',
            'AZURE_DEVOPS',
            'SONAR',
            'SQL',
            'TELEGRAM',
            'ZEPHYR_SCALE',
            '_ZEPHYR_CLOUD',
            'ZEPHYR_SQUAD',
            'XRAY',
            'SERVICENOW',
            'REPORT_PORTAL',
            'ENVIRONMENT_VARS',
            'AUTH_TOKEN',
            'A2A',
            'LITE_LLM',
            'DIAL',
            'SHAREPOINT',
        ],
        affected_columns=[TableReference(table_schema='codemie', table_name='settings', column_name='credential_type')],
        enum_values_to_rename=[],
    )
