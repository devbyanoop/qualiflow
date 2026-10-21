from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .generate_tests import ChunkNotFoundError, generate_tests_graph
from .hello_graph import hello_graph

app = FastAPI(title="QualiFlow Agents")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/hello/{name}")
def hello(name: str) -> dict:
    result = hello_graph.invoke({"name": name})
    return {"greeting": result["greeting"]}


class GenerateRequest(BaseModel):
    org_id: str
    feature_id: str
    instruction: str


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    # ainvoke, not invoke — this runs on the event loop this process
    # already has (the SelectorEventLoop built below), never a nested
    # asyncio.run(). retrieve_context is async (real DB I/O); mixing it
    # with invoke() would either block or try to spin up a second loop.
    try:
        result = await generate_tests_graph.ainvoke(
            {"org_id": req.org_id, "feature_id": req.feature_id, "instruction": req.instruction}
        )
    except ChunkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"case": result["case"], "retrieved_chunk": result["retrieved_chunk"]}


if __name__ == "__main__":
    # Same reasoning as apps/knowledge/main.py and apps/api/main.py —
    # uvicorn.run() hard-codes ProactorEventLoop on Windows regardless
    # of any policy set elsewhere. This app didn't need the fix until
    # /generate added real DB I/O just now.
    import asyncio
    import sys

    import uvicorn

    config = uvicorn.Config(app, host="0.0.0.0", port=8002)
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())
    else:
        asyncio.run(server.serve())
