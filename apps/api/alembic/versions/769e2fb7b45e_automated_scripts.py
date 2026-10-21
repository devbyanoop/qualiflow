"""automated scripts

Revision ID: 769e2fb7b45e
Revises: 651d0212825c
Create Date: 2026-10-21 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '769e2fb7b45e'
down_revision: Union[str, Sequence[str], None] = '651d0212825c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'automated_scripts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('feature_id', sa.String(), nullable=False),
        sa.Column('case_review_id', sa.String(), nullable=False),  # not a FK -- Walking Skeleton simplicity
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('output', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Same tenant-isolation pattern as every other table.
    op.execute("ALTER TABLE automated_scripts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE automated_scripts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_isolation ON automated_scripts "
        "USING (org_id = current_setting('app.current_org_id', true))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON automated_scripts TO qualiflow_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('automated_scripts')
