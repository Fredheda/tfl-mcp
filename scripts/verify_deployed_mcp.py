#!/usr/bin/env python3
"""Throwaway verification script: confirms the deployed tfl-mcp Function
App actually returns real TFL data over MCP for every tool, not just that
it's "Running".

Uses langchain_mcp_adapters.client.MultiServerMCPClient -- the
ecosystem-standard MCP-to-LangChain tool-loading bridge. Requires mcp
pinned <2.0.0 (see pyproject.toml):
langchain-mcp-adapters has no release compatible with mcp v2 as of this
writing (latest, 0.3.2, hard-pins mcp<2.0.0).

Usage: python3 scripts/verify_deployed_mcp.py [<line> ...]
Requires FUNCTION_APP_URL and FUNCTION_MCP_KEY in the environment or .env.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()


async def main(lines: list[str]) -> None:
    function_app_url = os.environ["FUNCTION_APP_URL"].rstrip("/")
    mcp_key = os.environ["FUNCTION_MCP_KEY"]
    client = MultiServerMCPClient(
        {
            "tfl": {
                "transport": "streamable_http",
                "url": f"{function_app_url}/runtime/webhooks/mcp",
                "headers": {"x-functions-key": mcp_key},
            }
        }
    )
    tools = await client.get_tools()
    print(f"Discovered tools: {[t.name for t in tools]}")
    calls = [
        ("get_tfl_status", {"lines": lines}),
        ("find_station", {"query": "waterloo"}),
        ("get_arrivals", {"stop_id": "940GZZLUWLO"}),
        ("plan_journey", {"origin": "940GZZLUWLO", "destination": "940GZZLUKSX"}),
    ]
    for name, args in calls:
        tool = next(t for t in tools if t.name == name)
        print(f"--- {name}")
        print(await tool.ainvoke(args))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["victoria"]))
