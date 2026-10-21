from qualiflow_agents.hello_graph import hello_graph


def test_hello_graph_returns_structured_greeting():
    """A real call, not mocked — needs OPENAI_API_KEY set. Costs a
    fraction of a cent (gpt-4o-mini) but is a genuine real-money,
    real-network call every time this runs."""
    result = hello_graph.invoke({"name": "Ada"})

    assert isinstance(result["greeting"], str)
    assert len(result["greeting"]) > 0
