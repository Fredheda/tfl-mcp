"""FastAPI app that serves the tfl-status LangGraph agent over A2A.

No auth-handling code here: once deployed, Container Apps' built-in auth
(Task 7's authConfig) validates every incoming request's Entra ID token
before it reaches this app at all. Locally, there is no such sidecar, so
every request is accepted -- this is deliberate and is what makes
local-to-local testing between this agent and a consumer's local dev
process work without any auth stubbing.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from tfl_status_agent.agent import GraphHolder
from tfl_status_agent.agent_executor import TflStatusAgentExecutor

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is not set. Create .env with OPENAI_API_KEY=...")
if not os.getenv("FUNCTION_APP_URL"):
    raise RuntimeError("FUNCTION_APP_URL is not set (the tfl-mcp Function App URL).")

PUBLIC_URL = os.getenv("TFL_STATUS_AGENT_PUBLIC_URL", "http://localhost:8002")
RPC_PATH = "/a2a"

agent_card = AgentCard(
    name="TFL Status Agent",
    description="Reports live status for London Underground and DLR lines.",
    supported_interfaces=[
        AgentInterface(protocol_binding="JSONRPC", url=f"{PUBLIC_URL}{RPC_PATH}")
    ],
    version="0.1.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[
        AgentSkill(
            id="tfl_status",
            name="Get TFL line status",
            description="Reports current status for one or more London Underground/DLR lines.",
            tags=["tfl", "transport", "london-underground"],
        )
    ],
)

graph_holder = GraphHolder()

request_handler = DefaultRequestHandler(
    agent_executor=TflStatusAgentExecutor(graph_holder),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await graph_holder.init_graph()
    yield


app = FastAPI(title="TFL Status A2A Agent", lifespan=lifespan)
add_a2a_routes_to_fastapi(
    app,
    agent_card_routes=create_agent_card_routes(agent_card=agent_card),
    jsonrpc_routes=create_jsonrpc_routes(
        request_handler=request_handler, rpc_url=RPC_PATH
    ),
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
