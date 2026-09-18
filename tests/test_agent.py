from unittest.mock import AsyncMock

from langchain_core.tools import tool

import tfl_status_agent.agent as agent


@tool
def fake_tool() -> str:
    """A fake tool standing in for a real MCP-loaded one."""
    return "fake"


async def test_init_graph_builds_graph_with_loaded_tools(monkeypatch):
    monkeypatch.setattr(agent, "load_mcp_tools", AsyncMock(return_value=[fake_tool]))
    holder = agent.GraphHolder()

    result = await holder.init_graph()

    assert holder.graph is result
    assert holder.graph is not None


async def test_init_graph_falls_back_to_no_tools_on_mcp_failure(monkeypatch):
    monkeypatch.setattr(
        agent, "load_mcp_tools", AsyncMock(side_effect=ConnectionError("unreachable"))
    )
    holder = agent.GraphHolder()

    result = await holder.init_graph()

    assert holder.graph is result
    assert holder.graph is not None


def test_build_model_uses_responses_api_with_reasoning_summaries():
    model = agent.build_model()

    assert model.model_name == "gpt-5.6-luna"
    assert model.use_responses_api is True
    assert model.output_version == "responses/v1"
    assert model.reasoning == {"effort": "low", "summary": "auto"}
