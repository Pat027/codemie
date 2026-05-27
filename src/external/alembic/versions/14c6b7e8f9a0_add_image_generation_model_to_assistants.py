"""add_image_generation_model_to_assistants

Revision ID: 14c6b7e8f9a0
Revises: j4k5l6m7n8o9
Create Date: 2026-05-12 15:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14c6b7e8f9a0'
down_revision: Union[str, None] = 'j4k5l6m7n8o9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add image generation settings to assistants, assistant configurations, and conversations."""
    op.add_column('assistants', sa.Column('image_generation_model', sa.String(), nullable=True))
    op.add_column('assistants', sa.Column('enable_image_generation', sa.Boolean(), nullable=True))

    op.add_column('assistant_configurations', sa.Column('image_generation_model', sa.String(), nullable=True))
    op.add_column('assistant_configurations', sa.Column('enable_image_generation', sa.Boolean(), nullable=True))

    op.add_column('conversations', sa.Column('image_generation_model', sa.String(), nullable=True))
    op.add_column('conversations', sa.Column('enable_image_generation', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Remove image generation settings from assistants, assistant configurations, and conversations."""
    op.drop_column('conversations', 'enable_image_generation')
    op.drop_column('conversations', 'image_generation_model')

    op.drop_column('assistant_configurations', 'enable_image_generation')
    op.drop_column('assistant_configurations', 'image_generation_model')

    op.drop_column('assistants', 'enable_image_generation')
    op.drop_column('assistants', 'image_generation_model')
