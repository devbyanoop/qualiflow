import uuid

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_agents.generate_tests import ChunkNotFoundError, build_graph
from qualiflow_agents.settings import settings

REQUIREMENT_TEXT = (
    "A customer may withdraw cash from an ATM up to their daily limit of $500. "
    "Withdrawals are rejected if they would exceed the remaining daily limit."
)
CHECKPOINTER_URI = settings.database_url.replace("postgresql+psycopg://", "postgresql://")


async def _seed_chunk(org_id: str, feature_id: str, content: str) -> None:
    """Seeds a row directly via the superuser connection, bypassing a
    real embedding call -- these tests are about retrieve_context's
    retrieval logic and draft_manual_cases' real LLM generation, not
    re-proving M0.6's embedding pipeline. The vector's actual values
    don't matter here, only that a row with this org/feature exists;
    a fixed dummy vector of the right dimension (384) is standard test
    fixture data, not a mock of anything under test."""
    engine = create_async_engine(settings.database_url_admin)
    dummy_vector = "[" + ",".join(["0.0"] * 384) + "]"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO knowledge_chunks (id, org_id, feature_id, doc_hash, chunk_hash, content, embedding) "
                "VALUES (:id, :org_id, :feature_id, :hash, :hash, :content, :embedding ::vector)"
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
    await engine.dispose()


# --- Positive ---------------------------------------------------------


@pytest.mark.asyncio
async def test_positive_generates_case_grounded_in_the_real_requirement():
    """Real LLM call (no mocking). Asserts more than 'it returned
    something' — checks the generated case actually reflects the
    specific requirement text, not a hallucinated generic case. This
    is the same check M0.7's build-plan milestone calls for: prove the
    retrieved chunk was actually used. Since M0.8, the graph pauses at
    human_review -- the drafted case is read from the interrupt value,
    not a final state key."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    await _seed_chunk(org_id, "atm", REQUIREMENT_TEXT)
    thread_id = f"{org_id}:atm:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer:
            graph = build_graph(checkpointer)
            paused = await graph.ainvoke(
                {"org_id": org_id, "feature_id": "atm", "instruction": "Generate a test case for this rule."},
                config=config,
            )
            pending = paused["__interrupt__"][0].value
            case = pending["case"]

            assert pending["retrieved_chunk"] == REQUIREMENT_TEXT
            assert case["title"]
            assert case["steps"]
            assert case["priority"] in {"low", "medium", "high", "critical"}
            # Grounded in the specific requirement, not generic — "500" or
            # "daily limit" should appear somewhere in the generated case.
            case_text = " ".join([case["title"], case["preconditions"], case["expected_result"]] + case["steps"])
            assert "500" in case_text or "daily limit" in case_text.lower()
    finally:
        await _cleanup(org_id)


# --- Negative -----------------------------------------------------------


@pytest.mark.asyncio
async def test_negative_missing_chunk_raises_chunk_not_found():
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"  # never seeded
    thread_id = f"{org_id}:does-not-exist:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer:
        graph = build_graph(checkpointer)
        with pytest.raises(ChunkNotFoundError):
            await graph.ainvoke(
                {"org_id": org_id, "feature_id": "does-not-exist", "instruction": "test"}, config=config
            )


# --- Edge ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_edge_empty_instruction_still_generates_a_valid_case():
    """Real LLM call. An empty instruction string is a real input a
    caller could send -- confirms it degrades gracefully (falls back
    to just the requirement) rather than crashing or returning junk."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    await _seed_chunk(org_id, "atm", REQUIREMENT_TEXT)
    thread_id = f"{org_id}:atm:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer:
            graph = build_graph(checkpointer)
            paused = await graph.ainvoke(
                {"org_id": org_id, "feature_id": "atm", "instruction": ""}, config=config
            )
            case = paused["__interrupt__"][0].value["case"]
            assert case["title"]
            assert case["steps"]
    finally:
        await _cleanup(org_id)


@pytest.mark.asyncio
async def test_edge_rls_isolation_holds_for_this_new_read_path():
    """Regression-guard as much as an edge case: M0.3 proved RLS isolates
    organizations/projects; this is a NEW consumer of knowledge_chunks
    (apps/agents, not apps/knowledge) reading via the same restricted
    qualiflow_app role. Confirms the isolation holds here too, not just
    where it was first proven -- a different org_id with the SAME
    feature_id must not see another org's chunk."""
    org_a = f"test-org-a-{uuid.uuid4().hex[:8]}"
    org_b = f"test-org-b-{uuid.uuid4().hex[:8]}"
    await _seed_chunk(org_a, "shared-feature-name", REQUIREMENT_TEXT)
    thread_id = f"{org_b}:shared-feature-name:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_URI) as checkpointer:
            graph = build_graph(checkpointer)
            with pytest.raises(ChunkNotFoundError):
                await graph.ainvoke(
                    {"org_id": org_b, "feature_id": "shared-feature-name", "instruction": "test"}, config=config
                )
    finally:
        await _cleanup(org_a)
        await _cleanup(org_b)
