import hashlib
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .chunking import chunk_by_heading
from .embeddings import embed


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


async def ingest(session: AsyncSession, org_id: str, feature_id: str, title: str, markdown: str) -> dict:
    """Real chunk-level delta-hash ingestion (plan §5.1), replacing
    M0.6's "whole document is one chunk" model. Document-level hash is
    checked first as a fast path -- an unchanged document skips parsing
    and chunking entirely. On a revision, each heading-section chunk is
    hashed individually and only chunks whose content actually changed
    get a new embedding call; unchanged sections are kept as-is."""
    # Set here, not left to each caller to remember -- the refactor out
    # of main.py's old inline logic dropped this once already (caught
    # by a real RLS "new row violates row-level security policy"
    # failure against the real database, not a mock). Doing it inside
    # ingest() itself means every caller, HTTP handler or test, gets it
    # automatically and can't forget it a second time.
    await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id})

    doc_hash = _hash(markdown)

    existing_doc = (
        await session.execute(
            text(
                "SELECT id, doc_hash FROM documents "
                "WHERE org_id = :org_id AND feature_id = :feature_id AND title = :title"
            ),
            {"org_id": org_id, "feature_id": feature_id, "title": title},
        )
    ).first()

    if existing_doc is not None and existing_doc.doc_hash == doc_hash:
        return {
            "document_id": existing_doc.id,
            "chunks_total": None,
            "chunks_embedded": 0,
            "chunks_reused": None,
            "skipped": True,
        }

    doc_id = existing_doc.id if existing_doc is not None else str(uuid.uuid4())

    drafts = chunk_by_heading(markdown)

    chunks_embedded = 0
    chunks_reused = 0
    kept_chunk_ids: list[str] = []

    for index, draft in enumerate(drafts):
        chunk_hash = _hash(draft.content)

        # Scoped to THIS document (doc_id), not every chunk in the
        # org/feature -- reuse must mean "unchanged since the last
        # version of this document", not "identical content happens to
        # exist somewhere else". Scoping it more broadly would let two
        # unrelated documents fight over the same chunk row whenever
        # their content happened to collide (e.g. shared boilerplate),
        # silently re-pointing it away from whichever was ingested
        # first every time the other one is re-ingested.
        existing_chunk = (
            await session.execute(
                text(
                    "SELECT id FROM knowledge_chunks "
                    "WHERE org_id = :org_id AND feature_id = :feature_id "
                    "AND doc_id = :doc_id AND chunk_hash = :chunk_hash"
                ),
                {"org_id": org_id, "feature_id": feature_id, "doc_id": doc_id, "chunk_hash": chunk_hash},
            )
        ).first()

        if existing_chunk is not None:
            chunk_id = existing_chunk.id
            await session.execute(
                text(
                    "UPDATE knowledge_chunks SET doc_hash = :doc_hash, heading = :heading, "
                    "chunk_index = :chunk_index WHERE id = :id"
                ),
                {"doc_hash": doc_hash, "heading": draft.heading, "chunk_index": index, "id": chunk_id},
            )
            chunks_reused += 1
        else:
            chunk_id = str(uuid.uuid4())
            vector = embed(draft.content)  # real TEI call -- only for genuinely new/changed content
            await session.execute(
                text(
                    "INSERT INTO knowledge_chunks "
                    "(id, org_id, feature_id, doc_id, doc_hash, chunk_hash, heading, chunk_index, "
                    "content, embedding) "
                    "VALUES (:id, :org_id, :feature_id, :doc_id, :doc_hash, :chunk_hash, :heading, "
                    ":chunk_index, :content, :embedding ::vector)"
                ),
                {
                    "id": chunk_id,
                    "org_id": org_id,
                    "feature_id": feature_id,
                    "doc_id": doc_id,
                    "doc_hash": doc_hash,
                    "chunk_hash": chunk_hash,
                    "heading": draft.heading,
                    "chunk_index": index,
                    "content": draft.content,
                    "embedding": _vector_literal(vector),
                },
            )
            chunks_embedded += 1

        kept_chunk_ids.append(chunk_id)

    # Sections present in the previous version but absent from this
    # one -- deleted outright, not tombstoned. Plan §5.1 names
    # versioning/tombstones as real future capabilities, but Phase 1's
    # literal scope here is chunk-level delta-hash; this is the honest,
    # simpler behavior for what's actually built, not silently assumed
    # to also cover history-keeping it doesn't.
    if kept_chunk_ids:
        placeholders = ", ".join(f":keep{i}" for i in range(len(kept_chunk_ids)))
        params = {f"keep{i}": cid for i, cid in enumerate(kept_chunk_ids)}
        params["doc_id"] = doc_id
        await session.execute(
            text(f"DELETE FROM knowledge_chunks WHERE doc_id = :doc_id AND id NOT IN ({placeholders})"),
            params,
        )
    else:
        await session.execute(text("DELETE FROM knowledge_chunks WHERE doc_id = :doc_id"), {"doc_id": doc_id})

    if existing_doc is not None:
        await session.execute(
            text("UPDATE documents SET doc_hash = :doc_hash WHERE id = :id"), {"doc_hash": doc_hash, "id": doc_id}
        )
    else:
        await session.execute(
            text(
                "INSERT INTO documents (id, org_id, feature_id, title, doc_hash) "
                "VALUES (:id, :org_id, :feature_id, :title, :doc_hash)"
            ),
            {"id": doc_id, "org_id": org_id, "feature_id": feature_id, "title": title, "doc_hash": doc_hash},
        )

    return {
        "document_id": doc_id,
        "chunks_total": len(drafts),
        "chunks_embedded": chunks_embedded,
        "chunks_reused": chunks_reused,
        "skipped": False,
    }
