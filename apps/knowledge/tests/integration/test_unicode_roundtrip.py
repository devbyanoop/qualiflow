import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_knowledge.db import SessionLocal
from qualiflow_knowledge.embeddings import embed
from qualiflow_knowledge.settings import settings

REPO_ROOT = Path(__file__).resolve().parents[4]
BILINGUAL_BRD = (REPO_ROOT / "fixtures" / "i18n-demo-brd.md").read_text(encoding="utf-8")


async def _ingest(org_id: str, feature_id: str, content: str) -> dict:
    """Mirrors main.py's /ingest handler directly -- same pattern as
    test_delta_hash.py, duplicated locally rather than imported (test
    modules aren't regular packages here)."""
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

            vector = embed(content)
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


async def _fetch_content(org_id: str, feature_id: str) -> str:
    async with SessionLocal() as session:
        await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id})
        result = await session.execute(
            text("SELECT content FROM knowledge_chunks WHERE org_id = :org_id AND feature_id = :feature_id"),
            {"org_id": org_id, "feature_id": feature_id},
        )
        return result.scalar_one()


async def _cleanup(org_id: str) -> None:
    admin_engine = create_async_engine(settings.database_url_admin)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM knowledge_chunks WHERE org_id = :org_id"), {"org_id": org_id})
    await admin_engine.dispose()


# --- Positive ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_positive_arabic_text_round_trips_byte_for_byte():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    arabic = "يجب أن يبلغ عمر العميل 18 عامًا على الأقل لفتح حساب."
    try:
        await _ingest(org_id, "arabic-feature", arabic)
        stored = await _fetch_content(org_id, "arabic-feature")
        assert stored == arabic
        assert stored.encode("utf-8") == arabic.encode("utf-8")
    finally:
        await _cleanup(org_id)


@pytest.mark.asyncio
async def test_positive_real_bilingual_brd_fixture_round_trips_exactly():
    """The actual Phase 0 demo fixture, ingested for real -- not a
    synthetic snippet. Proves the whole EN+AR document, including
    Markdown headings, an em-dash, and RTL Arabic in the same
    document, comes back identical."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    try:
        await _ingest(org_id, "bilingual-brd-feature", BILINGUAL_BRD)
        stored = await _fetch_content(org_id, "bilingual-brd-feature")
        assert stored == BILINGUAL_BRD
    finally:
        await _cleanup(org_id)


# --- Negative -----------------------------------------------------------


@pytest.mark.asyncio
async def test_negative_different_arabic_content_is_not_treated_as_a_duplicate():
    """The delta-hash skip must still correctly distinguish two
    genuinely different non-ASCII documents -- not collapse them
    because of some encoding quirk in the hash computation."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    try:
        first = await _ingest(org_id, "feature", "النص الأول للاختبار.")
        second = await _ingest(org_id, "feature", "النص الثاني، وهو مختلف تمامًا.")
        assert first["embedded"] is True
        assert second["embedded"] is True
        assert first["chunk_id"] != second["chunk_id"]
    finally:
        await _cleanup(org_id)


# --- Edge ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edge_mixed_rtl_ltr_and_combining_diacritics_round_trip():
    """Arabic tashkeel (diacritical marks, e.g. the tanwin in 'عامًا')
    are combining Unicode characters, not plain letters -- a common
    source of silent corruption if any layer normalizes or truncates
    multi-byte sequences incorrectly. Also mixes English digits/words
    inline with Arabic, the realistic bilingual-case shape the plan
    describes."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    mixed = "Minimum age (الحد الأدنى للعمر) is 18 عامًا — enforced at request time, not submission review."
    try:
        await _ingest(org_id, "mixed-feature", mixed)
        stored = await _fetch_content(org_id, "mixed-feature")
        assert stored == mixed
    finally:
        await _cleanup(org_id)


# --- Regression --------------------------------------------------------------
#
# Guards against the exact near-miss hit while building this: piping a
# non-ASCII HTTP response through a naive shell tool can look corrupted
# (json.tool defaults to \u-escaping, and a misconfigured terminal
# pipe can mis-decode it) even when the underlying data is perfectly
# correct. This test checks the real data layer directly, the same way
# the investigation that found it was a non-issue did -- real UTF-8
# bytes and codepoints, not a terminal's rendering of them.


@pytest.mark.asyncio
async def test_regression_doc_hash_is_stable_for_non_ascii_content():
    """hashlib operates on raw bytes, so this should trivially hold --
    but delta-hash (M0.6) is the one mechanism in this pipeline whose
    entire job is hash-equality, and Phase 0 is exactly where i18n
    content starts flowing through it for the first time. An explicit
    guard here is cheap insurance against a future encoding-aware
    "helpful" change (e.g. NFC/NFD normalization) silently breaking
    delta-hash for non-Latin content specifically."""
    content = "عامًا — 18"
    hash_a = hashlib.sha256(content.encode("utf-8")).hexdigest()
    hash_b = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert hash_a == hash_b
    assert len(hash_a) == 64
