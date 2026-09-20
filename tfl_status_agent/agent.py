"""LangGraph agent that answers TFL status, journey and arrivals questions, served over A2A.

Unlike a graph built from hand-defined tools, this one has a real tool
loaded live from the tfl-mcp Function App over MCP, so building the graph
is async and has to happen at FastAPI startup (tfl_status_agent/server.py's
lifespan) rather than at plain import time.
"""

import logging
from pathlib import Path

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from tfl_status_agent.mcp_client import load_mcp_tools
from tfl_status_agent.tools import get_current_time

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.md").read_text()


def build_model() -> ChatOpenAI:
    """The agent's chat model.

    Responses API + reasoning summaries, not chat completions: on the
    Responses API a reasoning model returns tool calls *and* a reasoning
    summary in the same turn, which is what lets the executor stream
    "why" lines alongside "what" lines. Built here (not at import) because
    ChatOpenAI needs OPENAI_API_KEY at construction and server.py checks
    for that key only after importing this module.
    """
    return ChatOpenAI(
        model="gpt-5.6-luna",
        use_responses_api=True,
        output_version="responses/v1",
        reasoning={"effort": "low", "summary": "auto"},
    )


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
        try:
            tools = await load_mcp_tools()
        except Exception:
            # A connection failure here previously crashed the whole
            # FastAPI lifespan (Application startup failed. Exiting.) --
            # confirmed live: deploying with an unreachable Function App
            # left the container stuck restarting forever, never becoming
            # healthy, while ingress silently kept routing to the last
            # healthy revision. Starting with no tools instead means the
            # process comes up and reports itself healthy; a query just
            # gets a plain-text answer with no tool call rather than the
            # whole agent being unreachable.
            logger.exception(
                "Failed to load MCP tools at startup; starting with no tools"
            )
            tools = []
        tools = [get_current_time, *tools]
        self.graph = create_agent(
            model=build_model(),
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=MemorySaver(),
        )
        return self.graph
