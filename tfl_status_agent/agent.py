"""LangGraph agent that answers TFL line-status questions, served over A2A.

Unlike a graph built from hand-defined tools, this one has a real tool
loaded live from the tfl-mcp Function App over MCP, so building the graph
is async and has to happen at FastAPI startup (tfl_status_agent/server.py's
lifespan) rather than at plain import time.
"""

from pathlib import Path

from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from tfl_status_agent.mcp_client import load_mcp_tools

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.md").read_text()


class GraphHolder:
    """Holds the graph singleton, built lazily after startup.

    server.py's FastAPI lifespan builds it once (init_graph is async, so it
    can't run at plain import time) and passes the same instance into the
    A2A executor's constructor, since a2a-sdk's `AgentExecutor.execute()`
    receives no `Request` and can't reach `app.state`/`Depends` on its own.
    """

    def __init__(self):
        self.graph = None

    async def init_graph(self):
        tools = await load_mcp_tools()
        self.graph = create_agent(
            model="openai:gpt-5.4-mini",
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=MemorySaver(),
        )
        return self.graph
