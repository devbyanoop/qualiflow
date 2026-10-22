import uuid

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_agents.generate_tests import build_graph
from qualiflow_agents.settings import settings

REQUIREMENT_TEXT = "A customer may withdraw cash up to their daily limit of $500."
CHECKPOINTER_URI = settings.database_url.replace("postgresql+psycopg://", "postgresql://")


async def _seed_chunk(org_id: str, feature_id: str, content: str) -> None:
    engine = create_async_engine(settings.database_url_admin)
    dummy_vector = "[" + ",".join(["0.0"] * 384) + "]"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO knowledge_chunks "
                "(id, org_id, feature_id, doc_hash, chunk_hash, chunk_index, content, embedding) "
                "VALUES (:id, :org_id, :feature_id, :hash, :hash, 0, :content, :embedding ::vector)"
            ),
            {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "feature_id": feature_id,
                "hash": uuid.uuid4().hex,
                "content": content,
                "embedding": dummy_vector,
            },
        )
    await engine.dispose()


async def _cleanup(org_id: str) -> None:
    engine = create_async_engine(settings.database_url_admin)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM knowledge_chunks WHERE org_id = :org_id"), {"org_id": org_id})
        await conn.execute(text("DELETE FROM case_reviews WHERE org_id = :org_id"), {"org_id": org_id})
    await engine.dispose()


# --- Positive -------------------------------------------------------------


@pytest.mark.asyncio
async def test_positive_generate_pauses_then_approve_resumes():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    await _seed_chunk(org_id, "atm", REQUIREMENT_TEXT)
    thread_id = f"{org_id}:atm:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer:
            graph = build_graph(checkpointer)

            paused = await graph.ainvoke(
                {"org_id": org_id, "feature_id": "atm", "instruction": "test"}, config=config
            )
            assert "__interrupt__" in paused
            pending = paused["__interrupt__"][0].value
            assert pending["case"]["title"]

            resumed = await graph.ainvoke(Command(resume={"action": "approve", "edited_case": None}), config=config)
            assert resumed["review_decision"]["action"] == "approve"
            assert resumed["case"] == pending["case"]
    finally:
        await _cleanup(org_id)


# --- Negative ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_negative_resume_on_never_started_thread_returns_empty_state():
    """Resuming a thread_id that was never invoked has no checkpoint at
    all -- aget_state returns an empty snapshot. main.py's /review
    endpoint turns this into a 404; this test checks the underlying
    LangGraph-level signal that decision is built on."""
    thread_id = f"never-started-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer:
        graph = build_graph(checkpointer)
        snapshot = await graph.aget_state(config)
        assert not snapshot.values


# --- Edge --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edge_reject_decision_short_circuits_with_no_final_case():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    await _seed_chunk(org_id, "atm", REQUIREMENT_TEXT)
    thread_id = f"{org_id}:atm:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer:
            graph = build_graph(checkpointer)
            await graph.ainvoke({"org_id": org_id, "feature_id": "atm", "instruction": "test"}, config=config)
            resumed = await graph.ainvoke(
                Command(resume={"action": "reject", "edited_case": None}), config=config
            )
            assert resumed["review_decision"]["action"] == "reject"
    finally:
        await _cleanup(org_id)


@pytest.mark.asyncio
async def test_edge_edit_decision_carries_the_edited_case_through():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    await _seed_chunk(org_id, "atm", REQUIREMENT_TEXT)
    thread_id = f"{org_id}:atm:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}
    edited = {
        "title": "edited",
        "preconditions": "p",
        "steps": ["s"],
        "test_data": "d",
        "expected_result": "e",
        "priority": "low",
    }

    try:
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer:
            graph = build_graph(checkpointer)
            await graph.ainvoke({"org_id": org_id, "feature_id": "atm", "instruction": "test"}, config=config)
            resumed = await graph.ainvoke(
                Command(resume={"action": "edit", "edited_case": edited}), config=config
            )
            assert resumed["review_decision"]["action"] == "edit"
            assert resumed["review_decision"]["edited_case"] == edited
    finally:
        await _cleanup(org_id)


# --- Regression --------------------------------------------------------------
#
# M0.8's whole point: interrupt() + a Postgres checkpointer is categorically
# different from "save a flag and poll" -- the full execution state must
# survive being resumed from an ENTIRELY SEPARATE graph/checkpointer
# instance, not just a second call on the same Python object. This is the
# automatable proxy for the real kill-and-restart proof already done
# manually (see docs/project/roadmap.md): a brand-new AsyncPostgresSaver
# connection, a brand-new compiled graph, resuming state written by a
# DIFFERENT graph instance entirely. If checkpointing ever silently
# degraded to in-memory-only, this is what would catch it.


@pytest.mark.asyncio
async def test_regression_state_survives_a_fully_independent_graph_instance():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    await _seed_chunk(org_id, "atm", REQUIREMENT_TEXT)
    thread_id = f"{org_id}:atm:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # "Process A": starts generation, pauses at the interrupt.
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer_a:
            graph_a = build_graph(checkpointer_a)
            paused = await graph_a.ainvoke(
                {"org_id": org_id, "feature_id": "atm", "instruction": "test"}, config=config
            )
            pending_case = paused["__interrupt__"][0].value["case"]
        # checkpointer_a's connection is now fully closed -- graph_a is
        # unreachable, exactly as if that process had been killed.

        # "Process B": a completely independent connection and graph,
        # resuming a thread it never started.
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer_b:
            graph_b = build_graph(checkpointer_b)
            resumed = await graph_b.ainvoke(
                Command(resume={"action": "approve", "edited_case": None}), config=config
            )
            assert resumed["case"] == pending_case
            assert resumed["review_decision"]["action"] == "approve"
    finally:
        await _cleanup(org_id)
