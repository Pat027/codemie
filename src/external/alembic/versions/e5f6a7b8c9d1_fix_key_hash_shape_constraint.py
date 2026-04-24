"""fix_key_hash_shape_constraint

Revision ID: e5f6a7b8c9d1
Revises: d4e5f6a7b8ca
Create Date: 2026-04-21 00:00:00.000000

The ck_project_spend_tracking_key_hash_shape constraint was created when only
'key' and 'budget' subject types existed.  Migration c2d3e4f5a6b7 added
'project_budget' and 'member_budget' but omitted updating this constraint,
causing CheckViolationError on every project_budget insert (key_hash IS NULL).

Fix: drop and recreate the constraint to allow NULL key_hash for all non-key
subject types.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d1"
down_revision: Union[str, None] = "d4e5f6a7b8ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_project_spend_tracking_key_hash_shape",
        "project_spend_tracking",
        type_="check",
    )
    op.create_check_constraint(
        "ck_project_spend_tracking_key_hash_shape",
        "project_spend_tracking",
        "(spend_subject_type = 'key' AND key_hash IS NOT NULL) OR "
        "(spend_subject_type IN ('budget', 'project_budget', 'member_budget') AND key_hash IS NULL) OR "
        "spend_subject_type IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_project_spend_tracking_key_hash_shape",
        "project_spend_tracking",
        type_="check",
    )
    op.create_check_constraint(
        "ck_project_spend_tracking_key_hash_shape",
        "project_spend_tracking",
        "(spend_subject_type = 'key' AND key_hash IS NOT NULL) OR "
        "(spend_subject_type = 'budget' AND key_hash IS NULL) OR "
        "spend_subject_type IS NULL",
    )
