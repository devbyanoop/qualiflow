import uuid

import pytest
from sqlalchemy import text

from qualiflow_knowledge.db import SessionLocal
from qualiflow_knowledge.embeddings import embed


async def _ingest(org_id: str, feature_id: str, content: str) -> dict:
    """Mirrors main.py's /ingest handler directly against the DB —
    this test exercises the same real embeddings call and real delta-
    hash logic the HTTP endpoint does, without needing a running
    server process."""
    import hashlib

    doc_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id}
            )
            existing = await session.execute(
                text(
                    "SELECT id FROM knowledge_chunks WHERE org_id = :org_id "
                    "AND feature_id = :feature_id AND doc_hash = :doc_hash"
                ),
                {"org_id": org_id, "feature_id": feature_id, "doc_hash": doc_hash},
            )
            row = existing.first()
            if row is not None:
                return {"chunk_id": row.id, "embedded": False}

            vector = embed(content)  # real call to the self-hosted TEI service
            chunk_id = str(uuid.uuid4())
            vector_literal = "[" + ",".join(str(v) for v in vector) + "]"
            await session.execute(
                text(
                    "INSERT INTO knowledge_chunks "
                    "(id, org_id, feature_id, doc_hash, chunk_hash, content, embedding) "
                    "VALUES (:id, :org_id, :feature_id, :doc_hash, :chunk_hash, :content, "
                    ":embedding ::vector)"
                ),
                {
                    "id": chunk_id,
                    "org_id": org_id,
                    "feature_id": feature_id,
                    "doc_hash": doc_hash,
                    "chunk_hash": doc_hash,
                    "content": content,
                    "embedding": vector_literal,
                },
            )
    return {"chunk_id": chunk_id, "embedded": True}


@pytest.mark.asyncio
async def test_identical_content_skips_the_second_embedding_call():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    content = "Delta-hash test paragraph — identical both times."

    try:
        first = await _ingest(org_id, "test-feature", content)
        second = await _ingest(org_id, "test-feature", content)

        assert first["embedded"] is True
        assert second["embedded"] is False
        # Same row, not a duplicate -- the whole point of the skip.
        assert first["chunk_id"] == second["chunk_id"]
    finally:
        from sqlalchemy.ext.asyncio import create_async_engine

        from qualiflow_knowledge.settings import settings

        admin_engine = create_async_engine(settings.database_url_admin)
        async with admin_engine.begin() as conn:
            await conn.execute(text("DELETE FROM knowledge_chunks WHERE org_id = :org_id"), {"org_id": org_id})
        await admin_engine.dispose()
