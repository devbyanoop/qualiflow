from fastapi import FastAPI, File, Form, UploadFile
from pydantic import BaseModel

from .db import SessionLocal
from .ingestion import ingest
from .parsing import parse_to_markdown

app = FastAPI(title="QualiFlow Knowledge")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


class IngestRequest(BaseModel):
    org_id: str
    feature_id: str
    title: str
    content: str


class IngestResponse(BaseModel):
    document_id: str
    chunks_total: int | None
    chunks_embedded: int
    chunks_reused: int | None
    skipped: bool


@app.post("/ingest", response_model=IngestResponse)
async def ingest_text(req: IngestRequest) -> IngestResponse:
    """Raw text/Markdown ingestion -- a pasted requirement, a ticket
    description, anything that's already text rather than a file to
    parse. `title` identifies this as one logical document across
    re-ingests (the delta-hash fast path and chunk-level reuse both key
    off org_id/feature_id/title), replacing M0.6's implicit "one
    content string per feature" model."""
    async with SessionLocal() as session:
        async with session.begin():
            result = await ingest(session, req.org_id, req.feature_id, req.title, req.content)
    return IngestResponse(**result)


@app.post("/ingest/document", response_model=IngestResponse)
async def ingest_document(
    org_id: str = Form(...),
    feature_id: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
) -> IngestResponse:
    """Real file upload -- PDF/DOCX/XLSX (anything Docling supports),
    parsed to heading-structured Markdown, then the same chunk-level
    delta-hash ingestion as the text path. This is the actual Phase 1
    "widen M0.6 to real documents" deliverable, not the text path
    (which already existed, just without title/chunking)."""
    data = await file.read()
    markdown = parse_to_markdown(file.filename or title, data)
    async with SessionLocal() as session:
        async with session.begin():
            result = await ingest(session, org_id, feature_id, title, markdown)
    return IngestResponse(**result)


if __name__ == "__main__":
    # NOT uvicorn.run(app, ...) -- uvicorn.Server.run() calls
    # asyncio_run(..., loop_factory=self.config.get_loop_factory()),
    # and that factory (uvicorn/loops/asyncio.py) directly instantiates
    # asyncio.ProactorEventLoop on Windows whenever workers==1 and
    # reload is off -- unconditionally, bypassing whatever event-loop
    # POLICY is set. The only real fix is to not let uvicorn pick the
    # loop at all: build our own SelectorEventLoop and drive
    # Server.serve() on it directly.
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
