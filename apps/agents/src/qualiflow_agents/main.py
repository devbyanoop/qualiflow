import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .api_automation_agent import dry_run, generate_pytest_script
from .evidence import store_evidence
from .generate_tests import ChunkNotFoundError, build_graph
from .hello_graph import hello_graph
from .settings import settings
from .targets import ProductionBlockedError, TargetNotFoundError, check_production_guardrail, get_target


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Opened ONCE for the process lifetime, not per-request — the
    # checkpointer needs a long-lived connection pool so a later
    # /review call (possibly after a restart) can still find state
    # from an earlier /generate call. Plain libpq URI, no +psycopg —
    # this isn't going through SQLAlchemy.
    checkpointer_uri = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(checkpointer_uri) as checkpointer:
        app.state.generate_tests_graph = build_graph(checkpointer)
        yield


app = FastAPI(title="QualiFlow Agents", lifespan=lifespan)

db_engine = create_async_engine(settings.database_url)


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
async def generate(req: GenerateRequest, request: Request) -> dict:
    # thread_id namespaced with org_id/feature_id — the checkpointer's
    # own tables have no org_id column (see scripts/setup_checkpointer.py's
    # docstring for why RLS doesn't cover them), so this is an
    # application-level mitigation, not a database-enforced guarantee.
    thread_id = f"{req.org_id}:{req.feature_id}:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await request.app.state.generate_tests_graph.ainvoke(
            {"org_id": req.org_id, "feature_id": req.feature_id, "instruction": req.instruction},
            config=config,
        )
    except ChunkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    interrupts = result.get("__interrupt__")
    if not interrupts:
        # Shouldn't happen — human_review always calls interrupt() —
        # but fail loudly rather than silently return an unreviewed case.
        raise HTTPException(status_code=500, detail="Graph did not pause for review as expected.")

    return {"thread_id": thread_id, "pending_review": interrupts[0].value}


TargetEnvironment = Literal["production", "pre-production", "uat", "qa", "dev"]


class TargetAppRequest(BaseModel):
    org_id: str
    feature_id: str
    base_url: str
    openapi_spec: str
    # §8.5's first safety guardrail: every target must be explicitly
    # classified -- no default, so a caller can't accidentally land a
    # target in "dev" (and get automated against freely) when it was
    # actually production. The Pydantic Literal rejects a bad value at
    # the API layer; the DB's CHECK constraint (migration
    # b2a7c419e3d5) rejects it a second way, for any caller that skips
    # this endpoint.
    environment: TargetEnvironment


@app.post("/targets")
async def register_target(req: TargetAppRequest) -> dict:
    """Registers the system under test for an org/feature -- what
    api_automation_agent.py used to hardcode as NovaPay's URL and
    fixtures/novapay/openapi.yaml. No credentials here: auth is
    supplied per /review request instead (see ReviewRequest.target_auth),
    never persisted. NovaPay is registered through this same endpoint
    like any other target, not a special case in code."""
    target_id = str(uuid.uuid4())
    async with db_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": req.org_id}
        )
        await conn.execute(
            text(
                "INSERT INTO target_apps (id, org_id, feature_id, base_url, openapi_spec, environment) "
                "VALUES (:id, :org_id, :feature_id, :base_url, :openapi_spec, :environment)"
            ),
            {
                "id": target_id,
                "org_id": req.org_id,
                "feature_id": req.feature_id,
                "base_url": req.base_url,
                "openapi_spec": req.openapi_spec,
                "environment": req.environment,
            },
        )
    return {"target_id": target_id}


class ReviewRequest(BaseModel):
    action: str  # "approve" | "edit" | "reject"
    edited_case: dict | None = None
    # Credentials the generated resolver/test script needs against the
    # registered target (e.g. {"username": ..., "password": ...}).
    # Required for approve/edit -- never persisted, used for this
    # request only.
    target_auth: dict | None = None
    # §8.5: production targets are blocked by default. This is the
    # explicit opt-in the plan calls for -- but it only lifts the
    # block, it does NOT verify the generated script is read-only.
    # Enforcing that (inspecting the script for write-shaped HTTP
    # calls) is §8.5's separate "Action policies" guardrail, not built
    # yet -- see docs/adr/0007-environment-classification.md.
    allow_production: bool = False


@app.post("/review/{thread_id}")
async def review(thread_id: str, req: ReviewRequest, request: Request) -> dict:
    if req.action not in {"approve", "edit", "reject"}:
        raise HTTPException(status_code=422, detail=f"Unknown action {req.action!r}")
    if req.action == "edit" and req.edited_case is None:
        raise HTTPException(status_code=422, detail="edited_case is required when action is 'edit'")
    if req.action in {"approve", "edit"} and not req.target_auth:
        raise HTTPException(status_code=422, detail="target_auth is required for action 'approve' or 'edit'")

    config = {"configurable": {"thread_id": thread_id}}
    graph = request.app.state.generate_tests_graph

    state_snapshot = await graph.aget_state(config)
    if not state_snapshot.values:
        raise HTTPException(status_code=404, detail=f"No pending review for thread_id={thread_id!r}")

    result = await graph.ainvoke(
        Command(resume={"action": req.action, "edited_case": req.edited_case}), config=config
    )

    org_id = result["org_id"]
    final_case = req.edited_case if req.action == "edit" else result["case"]
    case_review_id = str(uuid.uuid4())

    async with db_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id})
        await conn.execute(
            text(
                "INSERT INTO case_reviews (id, org_id, feature_id, thread_id, decision, original_case, edited_case) "
                "VALUES (:id, :org_id, :feature_id, :thread_id, :decision, :original_case ::jsonb, "
                ":edited_case ::jsonb)"
            ),
            {
                "id": case_review_id,
                "org_id": org_id,
                "feature_id": result["feature_id"],
                "thread_id": thread_id,
                "decision": req.action,
                "original_case": _to_json(result["case"]),
                "edited_case": _to_json(req.edited_case) if req.edited_case else None,
            },
        )

    response = {
        "thread_id": thread_id,
        "decision": req.action,
        "final_case": final_case if req.action != "reject" else None,
    }

    if req.action in {"approve", "edit"}:
        try:
            target = await get_target(org_id, result["feature_id"])
        except TargetNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

        try:
            check_production_guardrail(target, req.allow_production)
        except ProductionBlockedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None

        # api_automation_agent, M0.9/M0.10. Both generate_pytest_script
        # (litellm.completion, including the resolver sub-step) and
        # dry_run (subprocess.run) are blocking calls -- to_thread so
        # they don't stall this async handler's event loop for the
        # ~10-20s this takes.
        try:
            script = await asyncio.to_thread(
                generate_pytest_script, final_case, result["retrieved_chunk"], target, req.target_auth
            )
        except RuntimeError as exc:
            # The resolver ran for real against the real target and
            # genuinely failed (e.g. no data satisfies the case) -- a
            # real upstream failure, not a bug in our own code.
            raise HTTPException(status_code=502, detail=str(exc)) from None
        run_result = await asyncio.to_thread(dry_run, script)
        automated_script_id = str(uuid.uuid4())

        # M0.10: hash the real artifacts, store them + a manifest in
        # MinIO — this app's first actual use of the object storage
        # set up all the way back in M0.1.
        manifest = await asyncio.to_thread(
            store_evidence,
            org_id,
            result["feature_id"],
            automated_script_id,
            run_result["code"],
            run_result["output"],
            run_result["passed"],
        )

        async with db_engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id}
            )
            await conn.execute(
                text(
                    "INSERT INTO automated_scripts "
                    "(id, org_id, feature_id, case_review_id, code, passed, output, evidence) "
                    "VALUES (:id, :org_id, :feature_id, :case_review_id, :code, :passed, :output, "
                    ":evidence ::jsonb)"
                ),
                {
                    "id": automated_script_id,
                    "org_id": org_id,
                    "feature_id": result["feature_id"],
                    "case_review_id": case_review_id,
                    "code": run_result["code"],
                    "passed": run_result["passed"],
                    "output": run_result["output"],
                    "evidence": _to_json(manifest),
                },
            )

        response["automation"] = {
            "passed": run_result["passed"],
            "script_path": run_result["script_path"],
            "evidence_manifest": manifest,
        }

    return response


def _to_json(value: dict) -> str:
    import json

    return json.dumps(value)


if __name__ == "__main__":
    # Same reasoning as apps/knowledge/main.py and apps/api/main.py —
    # uvicorn.run() hard-codes ProactorEventLoop on Windows regardless
    # of any policy set elsewhere.
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
