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
