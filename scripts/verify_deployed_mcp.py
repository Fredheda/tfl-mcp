#!/usr/bin/env python3
"""Throwaway verification script: confirms the deployed tfl-mcp Function
App actually returns real TFL data over MCP, not just that it's "Running".

Uses langchain_mcp_adapters.client.MultiServerMCPClient -- same
library/pattern Portfolio's backend/agent/mcp_tools.py already uses for
its own MCP tool loading. Requires mcp pinned <2.0.0 (see pyproject.toml):
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
    tool = next(t for t in tools if t.name == "get_tfl_status")
    result = await tool.ainvoke({"lines": lines})
    print(result)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["victoria"]))
