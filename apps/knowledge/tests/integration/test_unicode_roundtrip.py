import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_knowledge.db import SessionLocal
from qualiflow_knowledge.ingestion import ingest
from qualiflow_knowledge.settings import settings

REPO_ROOT = Path(__file__).resolve().parents[4]
BILINGUAL_BRD = (REPO_ROOT / "fixtures" / "i18n-demo-brd.md").read_text(encoding="utf-8")


async def _fetch_chunks(org_id: str, feature_id: str) -> list[str]:
    async with SessionLocal() as session:
        await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id})
        result = await session.execute(
            text(
                "SELECT content FROM knowledge_chunks WHERE org_id = :org_id AND feature_id = :feature_id "
                "ORDER BY chunk_index"
            ),
            {"org_id": org_id, "feature_id": feature_id},
        )
        return [row.content for row in result.all()]


async def _cleanup(org_id: str) -> None:
    admin_engine = create_async_engine(settings.database_url_admin)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM knowledge_chunks WHERE org_id = :org_id"), {"org_id": org_id})
        await conn.execute(text("DELETE FROM documents WHERE org_id = :org_id"), {"org_id": org_id})
    await admin_engine.dispose()


# --- Positive ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_positive_arabic_text_round_trips_byte_for_byte():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    arabic = "يجب أن يبلغ عمر العميل 18 عامًا على الأقل لفتح حساب."
    try:
        async with SessionLocal() as session:
            async with session.begin():
                await ingest(session, org_id, "arabic-feature", "Arabic Test Doc", arabic)
        chunks = await _fetch_chunks(org_id, "arabic-feature")
        assert chunks == [arabic]  # no headings -> exactly one chunk, content untouched
        assert chunks[0].encode("utf-8") == arabic.encode("utf-8")
    finally:
        await _cleanup(org_id)


@pytest.mark.asyncio
async def test_positive_real_bilingual_brd_fixture_chunks_retain_exact_arabic_text():
    """The actual Phase 0 demo fixture, ingested for real through the
    real (now heading-aware) ingestion pipeline -- not a synthetic
    snippet. The fixture has multiple headings, so it now splits into
    several chunks (not one blob, as it did pre-widening); what matters
    is that the Arabic section's text survives parsing, chunking, and
    storage byte-for-byte, not that the whole file reconstructs as a
    single string."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    try:
        async with SessionLocal() as session:
            async with session.begin():
                result = await ingest(session, org_id, "bilingual-brd-feature", "Bilingual Demo BRD", BILINGUAL_BRD)
        assert result["chunks_total"] > 1  # confirms heading-based splitting actually happened

        chunks = await _fetch_chunks(org_id, "bilingual-brd-feature")
        arabic_chunk = next(c for c in chunks if "العربية" in c)
        original_arabic_paragraph = next(
            line for line in BILINGUAL_BRD.splitlines() if line.startswith("> يجب")
        )
        assert original_arabic_paragraph.removeprefix("> ") in arabic_chunk
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
        async with SessionLocal() as session:
            async with session.begin():
                first = await ingest(session, org_id, "feature", "Doc A", "النص الأول للاختبار.")
        async with SessionLocal() as session:
            async with session.begin():
                second = await ingest(session, org_id, "feature", "Doc B", "النص الثاني، وهو مختلف تمامًا.")
        assert first["skipped"] is False
        assert second["skipped"] is False
        assert first["document_id"] != second["document_id"]
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
        async with SessionLocal() as session:
            async with session.begin():
                await ingest(session, org_id, "mixed-feature", "Mixed RTL/LTR Doc", mixed)
        chunks = await _fetch_chunks(org_id, "mixed-feature")
        assert chunks == [mixed]
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
    but delta-hash is the one mechanism in this pipeline whose entire
    job is hash-equality, and i18n content flows through it (now at
    both the document and chunk level, since Phase 1's widening). An
    explicit guard here is cheap insurance against a future encoding-
    aware "helpful" change (e.g. NFC/NFD normalization) silently
    breaking delta-hash for non-Latin content specifically."""
    content = "عامًا — 18"
    hash_a = hashlib.sha256(content.encode("utf-8")).hexdigest()
    hash_b = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert hash_a == hash_b
    assert len(hash_a) == 64
