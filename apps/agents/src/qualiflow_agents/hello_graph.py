from typing import TypedDict

import litellm
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict

from .logging_utils import log_llm_call
from .tiers import resolve_tier


class Greeting(BaseModel):
    # extra="forbid" makes model_json_schema() include
    # "additionalProperties": false, which OpenAI's strict
    # structured-output mode requires to actually enforce the schema
    # rather than just hint at it.
    model_config = ConfigDict(extra="forbid")

    message: str


class HelloState(TypedDict):
    name: str
    greeting: str


def call_llm(state: HelloState) -> dict:
    tier = "qf-fast"
    model = resolve_tier(tier)

    with log_llm_call(tier, model) as finish:
        response = litellm.completion(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": f"Write a one-sentence friendly greeting for someone named {state['name']}.",
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "greeting",
                    "schema": Greeting.model_json_schema(),
                    "strict": True,
                },
            },
        )
        finish(response)

    # Validated here too, even though OpenAI's strict mode already
    # enforces the schema server-side — defense in depth, and the
    # thing to break on purpose (per the build plan's M0.4 "concepts
    # to own") is seeing what ValidationError actually looks like when
    # a model/provider that DOESN'T support strict mode returns
    # something that doesn't match.
    parsed = Greeting.model_validate_json(response.choices[0].message.content)
    return {"greeting": parsed.message}


def build_graph():
    graph = StateGraph(HelloState)
    graph.add_node("call_llm", call_llm)
    graph.set_entry_point("call_llm")
    graph.add_edge("call_llm", END)
    return graph.compile()


hello_graph = build_graph()
