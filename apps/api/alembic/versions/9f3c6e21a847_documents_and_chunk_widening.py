"""documents table and widened knowledge_chunks for real multi-chunk ingestion

Revision ID: 9f3c6e21a847
Revises: b2a7c419e3d5
Create Date: 2026-10-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f3c6e21a847'
down_revision: Union[str, Sequence[str], None] = 'b2a7c419e3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Phase 1 step 1 ("Knowledge base, widened"): M0.6 treated a whole
    # ingested document as exactly one chunk. Real documents (PDF/DOCX/
    # XLSX, parsed and split by heading) are many chunks per document,
    # so delta-hashing has to move from document-level to chunk-level --
    # re-embed only the sections that actually changed in a revised
    # document (plan §5.1), not the whole thing. `documents` tracks the
    # document itself (one row per upload); `knowledge_chunks` gains
    # doc_id, heading, and chunk_index to belong to one.
    op.create_table(
        'documents',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('feature_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('doc_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # A document-level fast path: if this exact (org, feature, title)'s
    # hash hasn't changed, skip parsing and chunking entirely (plan
    # §5.1's "document-level hashing skips unchanged files entirely"),
    # without even reaching the per-chunk comparison.
    op.create_index('ix_documents_org_feature_title', 'documents', ['org_id', 'feature_id', 'title'])

    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_isolation ON documents "
        "USING (org_id = current_setting('app.current_org_id', true))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON documents TO qualiflow_app")

    # Nullable: existing M0.6-era rows (single-chunk-per-feature,
    # pre-widening) stay as they are rather than being force-backfilled
    # with a synthetic document -- new ingests always set these.
    op.add_column('knowledge_chunks', sa.Column('doc_id', sa.String(), nullable=True))
    op.add_column('knowledge_chunks', sa.Column('heading', sa.Text(), nullable=True))
    op.add_column(
        'knowledge_chunks', sa.Column('chunk_index', sa.Integer(), nullable=False, server_default='0')
    )
    op.alter_column('knowledge_chunks', 'chunk_index', server_default=None)

    # Full-text search support for hybrid retrieval (plan §5.2: vector +
    # keyword/BM25-style search, to catch exact terms a vector search
    # can miss -- requirement IDs, field names, error codes). Added now
    # rather than in a second migration later. 'simple' config, not
    # 'english' -- this project ingests Arabic content too (the
    # bilingual demo BRD), and 'english' would apply English stemming
    # rules to non-English text; 'simple' just tokenizes/normalizes
    # without assuming a language.
    op.execute(
        "ALTER TABLE knowledge_chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute("CREATE INDEX ix_knowledge_chunks_content_tsv ON knowledge_chunks USING GIN (content_tsv)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_content_tsv")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS content_tsv")
    op.drop_column('knowledge_chunks', 'chunk_index')
    op.drop_column('knowledge_chunks', 'heading')
    op.drop_column('knowledge_chunks', 'doc_id')
    op.drop_table('documents')
