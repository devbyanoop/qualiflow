"""evidence manifest column

Revision ID: 4495e4bd985e
Revises: 769e2fb7b45e
Create Date: 2026-10-21 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '4495e4bd985e'
down_revision: Union[str, Sequence[str], None] = '769e2fb7b45e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('automated_scripts', sa.Column('evidence', JSONB(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('automated_scripts', 'evidence')
