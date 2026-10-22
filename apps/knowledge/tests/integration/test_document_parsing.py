import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_knowledge.chunking import chunk_by_heading
from qualiflow_knowledge.db import SessionLocal
from qualiflow_knowledge.ingestion import ingest
from qualiflow_knowledge.parsing import parse_to_markdown
from qualiflow_knowledge.settings import settings

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
BRD_V1 = FIXTURES_DIR / "brd_v1.docx"
BRD_V2 = FIXTURES_DIR / "brd_v2.docx"
COVERAGE_XLSX = FIXTURES_DIR / "coverage_matrix.xlsx"


async def _cleanup(org_id: str) -> None:
    engine = create_async_engine(settings.database_url_admin)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM knowledge_chunks WHERE org_id = :org_id"), {"org_id": org_id})
        await conn.execute(text("DELETE FROM documents WHERE org_id = :org_id"), {"org_id": org_id})
    await engine.dispose()


# --- Positive ---------------------------------------------------------------


def test_positive_docx_parses_to_heading_structured_markdown():
    """Real Docling parse of a real .docx -- not a synthetic string.
    Confirms headings survive as Markdown ATX headings (# / ##), which
    chunk_by_heading() depends on."""
    markdown = parse_to_markdown("brd_v1.docx", BRD_V1.read_bytes())
    assert "Account Opening Requirements" in markdown
    assert "Minimum Age" in markdown
    assert "Identity Verification" in markdown
    assert "#" in markdown  # genuinely has heading markup, not flattened to plain text


@pytest.mark.asyncio
async def test_positive_full_ingestion_of_a_real_docx_creates_one_chunk_per_heading():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    try:
        markdown = parse_to_markdown("brd_v1.docx", BRD_V1.read_bytes())
        async with SessionLocal() as session:
            async with session.begin():
                result = await ingest(session, org_id, "account-opening", "Account Opening BRD", markdown)

        assert result["skipped"] is False
        assert result["chunks_total"] == 3  # H1 intro, Minimum Age, Identity Verification
        assert result["chunks_embedded"] == 3
        assert result["chunks_reused"] == 0
    finally:
        await _cleanup(org_id)


@pytest.mark.asyncio
async def test_positive_xlsx_parses_and_ingests():
    """A different real format (XLSX, not DOCX) through the same
    pipeline -- proves parsing isn't DOCX-specific."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    try:
        markdown = parse_to_markdown("coverage_matrix.xlsx", COVERAGE_XLSX.read_bytes())
        async with SessionLocal() as session:
            async with session.begin():
                result = await ingest(session, org_id, "coverage", "Coverage Matrix", markdown)
        assert result["chunks_total"] >= 1
        assert result["chunks_embedded"] >= 1
    finally:
        await _cleanup(org_id)


# --- Negative -----------------------------------------------------------


@pytest.mark.asyncio
async def test_negative_identical_document_reingest_is_skipped_entirely():
    """The document-level fast path (plan §5.1): re-ingesting the exact
    same content must not even reach chunking, let alone re-embed
    anything."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    try:
        markdown = parse_to_markdown("brd_v1.docx", BRD_V1.read_bytes())
        async with SessionLocal() as session:
            async with session.begin():
                first = await ingest(session, org_id, "account-opening", "Account Opening BRD", markdown)
        async with SessionLocal() as session:
            async with session.begin():
                second = await ingest(session, org_id, "account-opening", "Account Opening BRD", markdown)

        assert first["skipped"] is False
        assert second["skipped"] is True
        assert second["chunks_embedded"] == 0
        assert second["document_id"] == first["document_id"]
    finally:
        await _cleanup(org_id)


# --- Edge ------------------------------------------------------------------


def test_edge_content_with_no_headings_becomes_one_chunk():
    chunks = chunk_by_heading("Just a plain paragraph with no heading markup at all.")
    assert len(chunks) == 1
    assert chunks[0].heading is None


def test_edge_empty_content_produces_no_chunks():
    assert chunk_by_heading("") == []
    assert chunk_by_heading("   \n\n  ") == []


def test_edge_heading_with_no_body_is_still_a_valid_chunk():
    chunks = chunk_by_heading("# Empty Section\n\n# Next Section\n\nHas content.")
    assert len(chunks) == 2
    assert chunks[0].heading == "Empty Section"
    assert chunks[0].content == "Empty Section"  # no body, just the heading text
    assert chunks[1].content == "Next Section\n\nHas content."


# --- Regression --------------------------------------------------------------


@pytest.mark.asyncio
async def test_regression_chunk_reuse_is_scoped_to_its_own_document():
    """The exact bug caught while writing ingestion.py: scoping chunk
    reuse to (org_id, feature_id, chunk_hash) alone -- not also doc_id
    -- would let a second, unrelated document with coincidentally
    identical section content steal that chunk row away from the first
    document. Two documents, same feature, one shared identical
    section: both must end up with their own chunk for it."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    shared_heading_markdown = "# Shared Boilerplate\n\nThis exact paragraph appears in both documents."
    try:
        async with SessionLocal() as session:
            async with session.begin():
                doc_a = await ingest(session, org_id, "shared-feature", "Document A", shared_heading_markdown)
        async with SessionLocal() as session:
            async with session.begin():
                doc_b = await ingest(session, org_id, "shared-feature", "Document B", shared_heading_markdown)

        assert doc_a["document_id"] != doc_b["document_id"]
        assert doc_a["chunks_embedded"] == 1
        # If the bug were present, doc_b's identical chunk would be
        # "reused" by stealing doc_a's row (chunks_embedded == 0) --
        # instead it must get its own real embedding, scoped to doc_b.
        assert doc_b["chunks_embedded"] == 1

        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id}
            )
            rows = (
                await session.execute(
                    text("SELECT doc_id FROM knowledge_chunks WHERE org_id = :org_id"), {"org_id": org_id}
                )
            ).all()
        doc_ids = {row.doc_id for row in rows}
        assert doc_ids == {doc_a["document_id"], doc_b["document_id"]}
    finally:
        await _cleanup(org_id)


@pytest.mark.asyncio
async def test_regression_revised_document_only_reembeds_the_changed_section():
    """The actual Phase 1 "done when": re-ingesting a revised document
    re-embeds only the section that changed (Minimum Age), while an
    untouched section (Identity Verification) keeps its exact chunk
    row -- proven by checking the chunk id itself stays the same, not
    just that the test "passes"."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    try:
        v1_markdown = parse_to_markdown("brd_v1.docx", BRD_V1.read_bytes())
        async with SessionLocal() as session:
            async with session.begin():
                v1_result = await ingest(session, org_id, "account-opening", "Account Opening BRD", v1_markdown)
        assert v1_result["chunks_embedded"] == 3

        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id}
            )
            v1_chunks = (
                await session.execute(
                    text(
                        "SELECT id, heading FROM knowledge_chunks "
                        "WHERE org_id = :org_id ORDER BY chunk_index"
                    ),
                    {"org_id": org_id},
                )
            ).all()
        identity_chunk_id = next(r.id for r in v1_chunks if r.heading == "Identity Verification")
        age_chunk_id_v1 = next(r.id for r in v1_chunks if r.heading == "Minimum Age")

        v2_markdown = parse_to_markdown("brd_v2.docx", BRD_V2.read_bytes())
        async with SessionLocal() as session:
            async with session.begin():
                v2_result = await ingest(session, org_id, "account-opening", "Account Opening BRD", v2_markdown)

        # Only the revised section triggers a real embedding call.
        assert v2_result["chunks_embedded"] == 1
        assert v2_result["chunks_reused"] == 2
        assert v2_result["document_id"] == v1_result["document_id"]

        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id}
            )
            v2_chunks = (
                await session.execute(
                    text("SELECT id, heading, content FROM knowledge_chunks WHERE org_id = :org_id"),
                    {"org_id": org_id},
                )
            ).all()

        identity_chunk_v2 = next(r for r in v2_chunks if r.heading == "Identity Verification")
        age_chunk_v2 = next(r for r in v2_chunks if r.heading == "Minimum Age")

        # Unchanged section: the exact same row, not a new one with
        # identical content.
        assert identity_chunk_v2.id == identity_chunk_id
        # Changed section: a genuinely new row, and the new wording is
        # really there.
        assert age_chunk_v2.id != age_chunk_id_v1
        assert "21" in age_chunk_v2.content
    finally:
        await _cleanup(org_id)
