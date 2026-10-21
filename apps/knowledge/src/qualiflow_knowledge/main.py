import hashlib
import uuid

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from .db import SessionLocal
from .embeddings import embed

app = FastAPI(title="QualiFlow Knowledge")


class IngestRequest(BaseModel):
    org_id: str
    feature_id: str
    content: str


class IngestResponse(BaseModel):
    chunk_id: str
    doc_hash: str
    embedded: bool  # False means the delta-hash skip fired — no embedding call made


def _vector_literal(vector: list[float]) -> str:
    # Raw SQL needs pgvector's text literal format explicitly — unlike
    # the ORM path, psycopg has no type info here to adapt a plain
    # Python list on its own.
    return "[" + ",".join(str(v) for v in vector) + "]"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest) -> IngestResponse:
    doc_hash = hashlib.sha256(req.content.encode("utf-8")).hexdigest()

    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"),
                {"org_id": req.org_id},
            )

            existing = await session.execute(
                text(
                    "SELECT id FROM knowledge_chunks WHERE org_id = :org_id "
                    "AND feature_id = :feature_id AND doc_hash = :doc_hash"
                ),
                {"org_id": req.org_id, "feature_id": req.feature_id, "doc_hash": doc_hash},
            )
            row = existing.first()
            if row is not None:
                # Delta-hash skip (§5.1) — identical content already
                # embedded under this org/feature; zero embedding calls.
                return IngestResponse(chunk_id=row.id, doc_hash=doc_hash, embedded=False)

            vector = embed(req.content)
            chunk_id = str(uuid.uuid4())
            await session.execute(
                text(
                    "INSERT INTO knowledge_chunks "
                    "(id, org_id, feature_id, doc_hash, chunk_hash, content, embedding) "
                    "VALUES (:id, :org_id, :feature_id, :doc_hash, :chunk_hash, :content, "
                    # Space before :: is required -- SQLAlchemy's text()
                    # bind-parameter parser treats ":embedding::vector"
                    # (no space) as Postgres's cast operator and leaves
                    # ":embedding" completely unprocessed rather than
                    # substituting it, with no compile-time error.
                    ":embedding ::vector)"
                ),
                {
                    "id": chunk_id,
                    "org_id": req.org_id,
                    "feature_id": req.feature_id,
                    "doc_hash": doc_hash,
                    "chunk_hash": doc_hash,  # single chunk == whole doc, for now
                    "content": req.content,
                    "embedding": _vector_literal(vector),
                },
            )

    return IngestResponse(chunk_id=chunk_id, doc_hash=doc_hash, embedded=True)


if __name__ == "__main__":
    # NOT uvicorn.run(app, ...) — uvicorn.Server.run() calls
    # asyncio_run(..., loop_factory=self.config.get_loop_factory()),
    # and that factory (uvicorn/loops/asyncio.py) directly instantiates
    # asyncio.ProactorEventLoop on Windows whenever workers==1 and
    # reload is off — unconditionally, bypassing whatever event-loop
    # POLICY is set (the __init__.py fix affects the policy, which
    # this code path never consults). The only real fix is to not let
    # uvicorn pick the loop at all: build our own SelectorEventLoop and
    # drive Server.serve() on it directly.
    import asyncio
    import sys

    import uvicorn

    config = uvicorn.Config(app, host="0.0.0.0", port=8003)
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())
    else:
        asyncio.run(server.serve())
