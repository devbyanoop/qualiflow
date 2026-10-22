import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_knowledge.db import SessionLocal
from qualiflow_knowledge.ingestion import ingest
from qualiflow_knowledge.settings import settings


async def _cleanup(org_id: str) -> None:
    admin_engine = create_async_engine(settings.database_url_admin)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM knowledge_chunks WHERE org_id = :org_id"), {"org_id": org_id})
        await conn.execute(text("DELETE FROM documents WHERE org_id = :org_id"), {"org_id": org_id})
    await admin_engine.dispose()


@pytest.mark.asyncio
async def test_identical_content_skips_the_second_embedding_call():
    """Calls the real ingestion.ingest() directly -- the same function
    both HTTP endpoints use -- rather than duplicating its logic in a
    local test helper (M0.6's original approach, which drifted out of
    sync with the real handler once Phase 1 widened it)."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    content = "Delta-hash test paragraph — identical both times."

    try:
        async with SessionLocal() as session:
            async with session.begin():
                first = await ingest(session, org_id, "test-feature", "Delta Hash Test Doc", content)
        async with SessionLocal() as session:
            async with session.begin():
                second = await ingest(session, org_id, "test-feature", "Delta Hash Test Doc", content)

        assert first["skipped"] is False
        assert second["skipped"] is True
        # Same document, not a duplicate -- the whole point of the skip.
        assert first["document_id"] == second["document_id"]
    finally:
        await _cleanup(org_id)
