#!/usr/bin/env python3
"""Throwaway verification script: confirms the deployed tfl-mcp Function
App actually returns real TFL data over MCP, not just that it's "Running".

Uses mcp's own v2 client directly (not langchain-mcp-adapters -- as of this
writing that package's latest release, 0.3.2, hard-pins mcp<2.0.0 and has
no release compatible with mcp v2; see this repo's plan for the deviation
note).

Usage: python3 scripts/verify_deployed_mcp.py [<line> ...]
Requires FUNCTION_APP_URL and FUNCTION_MCP_KEY in the environment or .env.
"""
import asyncio
import os
import sys

import httpx2
from dotenv import load_dotenv
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

load_dotenv()


async def main(lines: list[str]) -> None:
    function_app_url = os.environ["FUNCTION_APP_URL"].rstrip("/")
    mcp_key = os.environ["FUNCTION_MCP_KEY"]
    mcp_url = f"{function_app_url}/runtime/webhooks/mcp"

    async with httpx2.AsyncClient(headers={"x-functions-key": mcp_key}) as http_client:
        transport = streamable_http_client(mcp_url, http_client=http_client)
        async with Client(transport) as client:
            tools_result = await client.list_tools()
            print(f"Discovered tools: {[t.name for t in tools_result.tools]}")

            result = await client.call_tool("get_tfl_status", {"lines": lines})
            if result.is_error:
                print(f"Tool call failed: {result.content}")
                return
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["victoria"]))
