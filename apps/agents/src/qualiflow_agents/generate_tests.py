from typing import Literal, TypedDict

import litellm
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .logging_utils import log_llm_call
from .settings import settings
from .tiers import resolve_tier

engine = create_async_engine(settings.database_url)


class ManualTestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    preconditions: str
    steps: list[str]
    test_data: str
    expected_result: str
    priority: Literal["low", "medium", "high", "critical"]


class ChunkNotFoundError(ValueError):
    """Raised by retrieve_context when org_id/feature_id has no
    ingested chunk yet — a real, expected failure mode, not a bug."""


class GenerateState(TypedDict):
    org_id: str
    feature_id: str
    instruction: str
    retrieved_chunk: str
    case: dict  # ManualTestCase.model_dump()
    review_decision: dict  # {"action": "approve"|"edit"|"reject", "edited_case": dict|None}


async def retrieve_context(state: GenerateState) -> dict:
    """No real search yet (that's Phase 1's hybrid search + reranker,
    §5.2) — just fetch the one chunk stored for this org/feature.
    Proves the retrieval wiring before there's more than one chunk to
    choose between."""
    async with engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": state["org_id"]}
        )
        result = await conn.execute(
            text(
                "SELECT content FROM knowledge_chunks "
                "WHERE org_id = :org_id AND feature_id = :feature_id LIMIT 1"
            ),
            {"org_id": state["org_id"], "feature_id": state["feature_id"]},
        )
        row = result.first()

    if row is None:
        raise ChunkNotFoundError(
            f"No knowledge chunk for org_id={state['org_id']!r} feature_id={state['feature_id']!r}. "
            "Ingest one via apps/knowledge's /ingest first."
        )
    return {"retrieved_chunk": row.content}


def draft_manual_cases(state: GenerateState) -> dict:
    tier = "qf-balanced"
    model = resolve_tier(tier)

    prompt = (
        "You are drafting a manual QA test case from a business requirement.\n\n"
        f"Requirement:\n{state['retrieved_chunk']}\n\n"
        f"Instruction: {state['instruction']}\n\n"
        "Write one manual test case that verifies this requirement."
    )

    with log_llm_call(tier, model) as finish:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "manual_test_case",
                    "schema": ManualTestCase.model_json_schema(),
                    "strict": True,
                },
            },
        )
        finish(response)

    parsed = ManualTestCase.model_validate_json(response.choices[0].message.content)
    return {"case": parsed.model_dump()}


def human_review(state: GenerateState) -> dict:
    """interrupt() pauses graph execution here and hands the drafted
    case back to the caller. Resuming (a separate request, possibly a
    separate process, possibly after a restart) requires invoking the
    graph again with the SAME thread_id and Command(resume=decision) —
    LangGraph's checkpointer (Postgres-backed, see scripts/
    setup_checkpointer.py) restores the entire execution state, not
    just a flag some code checks."""
    decision = interrupt({"case": state["case"], "retrieved_chunk": state["retrieved_chunk"]})
    return {"review_decision": decision}


def build_graph(checkpointer=None):
    # No checkpointer -> compiles fine but interrupt()/resume can't
    # survive past a single ainvoke call (nothing persists state
    # between calls). Always pass one outside of quick manual testing.
    graph = StateGraph(GenerateState)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("draft_manual_cases", draft_manual_cases)
    graph.add_node("human_review", human_review)
    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "draft_manual_cases")
    graph.add_edge("draft_manual_cases", "human_review")
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer)
