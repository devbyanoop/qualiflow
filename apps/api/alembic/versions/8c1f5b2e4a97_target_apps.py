"""target apps

Revision ID: 8c1f5b2e4a97
Revises: 4495e4bd985e
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c1f5b2e4a97'
down_revision: Union[str, Sequence[str], None] = '4495e4bd985e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The system under test, per org/feature -- replaces the NovaPay
    # URL/spec constants that were hardcoded into api_automation_agent.py.
    # Deliberately no credentials column: auth is supplied per /generate
    # or /review request, never persisted here. Storing secrets at rest
    # is a real security decision (encryption, rotation, access control)
    # that hasn't been made yet -- not something to default into quietly.
    op.create_table(
        'target_apps',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('feature_id', sa.String(), nullable=False),
        sa.Column('base_url', sa.String(), nullable=False),
        sa.Column('openapi_spec', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_target_apps_org_feature', 'target_apps', ['org_id', 'feature_id'])

    op.execute("ALTER TABLE target_apps ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE target_apps FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_isolation ON target_apps "
        "USING (org_id = current_setting('app.current_org_id', true))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON target_apps TO qualiflow_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('target_apps')
