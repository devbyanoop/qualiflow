"""target environment classification

Revision ID: b2a7c419e3d5
Revises: 8c1f5b2e4a97
Create Date: 2026-10-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2a7c419e3d5'
down_revision: Union[str, Sequence[str], None] = '8c1f5b2e4a97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # §8.5's first guardrail: every target app must be explicitly
    # classified. No default -- an unclassified target is a mistake to
    # surface at registration time, not something to quietly assume
    # "dev" or "production" for. The CHECK constraint, not just Pydantic
    # validation, is what actually prevents a bad value reaching the
    # table a second way (direct SQL, a future caller that skips the
    # API layer).
    # Added with a temporary server_default so existing rows (dev-only
    # data from before this guardrail existed) backfill to "dev" rather
    # than failing the NOT NULL; the default is dropped immediately
    # after so every future INSERT must specify environment explicitly.
    op.add_column(
        'target_apps', sa.Column('environment', sa.String(), nullable=False, server_default='dev')
    )
    op.alter_column('target_apps', 'environment', server_default=None)
    op.create_check_constraint(
        'ck_target_apps_environment',
        'target_apps',
        "environment IN ('production', 'pre-production', 'uat', 'qa', 'dev')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_target_apps_environment', 'target_apps', type_='check')
    op.drop_column('target_apps', 'environment')
