"""case reviews for the human gate

Revision ID: 651d0212825c
Revises: ae3bdda90862
Create Date: 2026-10-21 17:46:04.161086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '651d0212825c'
down_revision: Union[str, Sequence[str], None] = 'ae3bdda90862'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'case_reviews',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('feature_id', sa.String(), nullable=False),
        sa.Column('thread_id', sa.String(), nullable=False),
        sa.Column('decision', sa.String(), nullable=False),  # approve | edit | reject
        sa.Column('original_case', JSONB(), nullable=False),
        sa.Column('edited_case', JSONB(), nullable=True),  # set only when decision == 'edit'
        sa.Column('reviewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_case_reviews_thread_id', 'case_reviews', ['thread_id'])

    # Same tenant-isolation pattern as every other table (M0.3, M0.6).
    op.execute("ALTER TABLE case_reviews ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE case_reviews FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_isolation ON case_reviews "
        "USING (org_id = current_setting('app.current_org_id', true))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON case_reviews TO qualiflow_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('case_reviews')
