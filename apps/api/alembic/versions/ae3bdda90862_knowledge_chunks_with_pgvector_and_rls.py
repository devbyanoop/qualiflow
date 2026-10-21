"""knowledge chunks with pgvector and RLS

Revision ID: ae3bdda90862
Revises: 5662e94618ff
Create Date: 2026-10-21 17:00:34.698504

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'ae3bdda90862'
down_revision: Union[str, Sequence[str], None] = '5662e94618ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 384 dims -- paraphrase-multilingual-MiniLM-L12-v2's real output
    # size, confirmed against the running embeddings service (M0.6),
    # not assumed from memory. Originally BAAI/bge-m3 (1024 dims), but
    # that model OOM-killed repeatedly even at ~11GB VM memory -- see
    # docker-compose.yml's embeddings service comment and
    # docs/project/roadmap.md for the full story.
    op.create_table(
        'knowledge_chunks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('feature_id', sa.String(), nullable=False),
        sa.Column('doc_hash', sa.String(), nullable=False),
        sa.Column('chunk_hash', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # The delta-hash skip (M0.6's "done when": re-uploading identical
    # content makes zero new embedding calls) filters on exactly these
    # three columns -- index them together.
    op.create_index(
        'ix_knowledge_chunks_delta_hash',
        'knowledge_chunks',
        ['org_id', 'feature_id', 'doc_hash'],
    )

    # Same tenant-isolation pattern as organizations/projects (M0.3) --
    # ENABLE + FORCE RLS, a policy on app.current_org_id, GRANT to the
    # restricted qualiflow_app role (never the superuser).
    op.execute("ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE knowledge_chunks FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_isolation ON knowledge_chunks "
        "USING (org_id = current_setting('app.current_org_id', true))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_chunks TO qualiflow_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('knowledge_chunks')
