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

"""add project+slug unique index to assistants (human-readable URLs)

Revision ID: a1b3e5d7f9c2
Revises: r7s8t9u0v1w2
Create Date: 2026-06-25 00:00:00.000000

Backfills a slug for existing assistants (derived from their name), resolves any
duplicate (project, slug) pairs by nullifying the losers (keeping the earliest),
then adds a partial unique index so slugs are unique within a project. NULL slugs
are exempt from the constraint, so assistants whose name has no slug-eligible
characters stay addressable by GUID.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b3e5d7f9c2'
down_revision: Union[str, None] = 'r7s8t9u0v1w2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Postgres mirror of codemie.core.utils.slugify:
#   lower -> whitespace/underscore to '-' -> drop chars outside [a-z0-9-]
#   -> collapse '-' runs -> trim leading/trailing '-'
_SLUG_EXPR = (
    "trim(both '-' from "
    "regexp_replace("
    "regexp_replace("
    "regexp_replace(lower(name), '[[:space:]_]', '-', 'g'), "
    "'[^a-z0-9-]', '', 'g'), "
    "'-+', '-', 'g'))"
)


def upgrade() -> None:
    """Backfill slugs, de-duplicate per project, and add the unique index."""
    # 1. Backfill a slug for assistants that don't have one yet. Names that yield an
    #    empty slug (e.g. only non-latin characters) are left NULL on purpose.
    op.execute(
        f"""
        UPDATE assistants
        SET slug = {_SLUG_EXPR}
        WHERE (slug IS NULL OR slug = '')
          AND {_SLUG_EXPR} <> ''
        """
    )

    # 2. Nullify any remaining empty-string slugs. After step 1, rows whose name
    #    produces no slug-eligible characters still carry slug = ''. The index
    #    condition (slug IS NOT NULL) includes empty strings, so they must be
    #    cleared before the index is created.
    op.execute("UPDATE assistants SET slug = NULL WHERE slug = ''")

    # 3. Resolve duplicate (project, slug) pairs (pre-existing or just backfilled):
    #    keep the earliest assistant's slug, suffix the rest with a deterministic,
    #    slug-safe fragment of their id so the new unique index can be created.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY project, slug
                       ORDER BY created_date NULLS FIRST, id
                   ) AS rn
            FROM assistants
            WHERE slug IS NOT NULL
        )
        UPDATE assistants a
        SET slug = a.slug || '-' || substr(md5(a.id::text), 1, 12)
        FROM ranked r
        WHERE a.id = r.id AND r.rn > 1
        """
    )

    # 4. Enforce per-project slug uniqueness. NULL slugs are excluded.
    op.create_index(
        "uq_assistants_project_slug",
        "assistants",
        ["project", "slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the unique index."""
    op.drop_index("uq_assistants_project_slug", table_name="assistants")
