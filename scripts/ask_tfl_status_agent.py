#!/usr/bin/env python3
"""Calls a running tfl-status agent directly over A2A -- similar client
shape to a plain httpx.AsyncClient()-based A2A caller, but with an explicit
60s timeout instead of httpx's 5s default.

A real end-to-end call here (A2A -> LangGraph -> MCP tool -> live TFL API)
takes 15-20+ seconds: MultiServerMCPClient opens and tears down a fresh MCP
session per tool call (confirmed via debug logging -- each session
open/close round trip against the deployed Function App took ~6s on its
own), on top of two LLM round trips (reasoning, then relaying the tool
result). httpx's 5s default timeout reads as a hang (ReadTimeout) even
though the request is progressing normally -- there is no actual bug, just
real latency that needs a longer client timeout.

Usage: python3 scripts/ask_tfl_status_agent.py "victoria line status" [base_url] [bearer_token]
"""
import asyncio
import sys
import uuid

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text
from a2a.types import Message, Part, Role, SendMessageRequest


async def main(query: str, base_url: str, token: str | None) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as httpx_client:
        client = await create_client(
            base_url,
            client_config=ClientConfig(httpx_client=httpx_client, streaming=False),
        )
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=query)],
        )
        async for response in client.send_message(SendMessageRequest(message=message)):
            if response.HasField("task") and response.task.artifacts:
                print("\n".join(get_artifact_text(a) for a in response.task.artifacts))
                return
            if response.HasField("message"):
                print(get_message_text(response.message))
                return
    print("No response received.")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "victoria line status"
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8002"
    token = sys.argv[3] if len(sys.argv) > 3 else None
    asyncio.run(main(query, base_url, token))
