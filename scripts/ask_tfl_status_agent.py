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

Streams by default: WORKING status updates are printed as they arrive as
`[kind] text` lines, then the final artifact. Pass --blocking to force the
old single-response call (useful to confirm the server still serves
non-streaming callers).

Usage: python3 scripts/ask_tfl_status_agent.py "victoria line status" [base_url] [bearer_token] [--blocking]
"""
import asyncio
import sys
import time
import uuid

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState


async def main(query: str, base_url: str, token: str | None, streaming: bool) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.monotonic()
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as httpx_client:
        client = await create_client(
            base_url,
            client_config=ClientConfig(httpx_client=httpx_client, streaming=streaming),
        )
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=query)],
        )
        artifacts: list[str] = []
        async for response in client.send_message(SendMessageRequest(message=message)):
            if response.HasField("status_update"):
                event = response.status_update
                if event.status.state == TaskState.TASK_STATE_WORKING and event.status.HasField("message"):
                    kind = event.metadata["kind"] if "kind" in event.metadata else "info"
                    elapsed = time.monotonic() - started
                    print(f"  [{elapsed:5.1f}s] [{kind}] {get_message_text(event.status.message)}")
            elif response.HasField("artifact_update"):
                artifacts.append(get_artifact_text(response.artifact_update.artifact))
            elif response.HasField("task") and response.task.artifacts:
                artifacts.extend(get_artifact_text(a) for a in response.task.artifacts)
            elif response.HasField("message"):
                artifacts.append(get_message_text(response.message))
    joined = "\n".join(artifacts) if artifacts else "No response received."
    print(f"\n{joined}")
    print(f"\n(total {time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--blocking"]
    query = args[0] if len(args) > 0 else "victoria line status"
    base_url = args[1] if len(args) > 1 else "http://localhost:8002"
    token = args[2] if len(args) > 2 else None
    asyncio.run(main(query, base_url, token, streaming="--blocking" not in sys.argv))
