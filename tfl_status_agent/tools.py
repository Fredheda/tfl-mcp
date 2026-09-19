"""Tools that run inside the agent process (not loaded over MCP)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

LONDON = ZoneInfo("Europe/London")


def _now() -> datetime:
    """Current London time. A seam so tests can pin the clock."""
    return datetime.now(LONDON)


@tool
def get_current_time() -> str:
    """Get the current date and time in London (local time, BST or GMT).

    Call this before plan_journey whenever the user gives a relative or
    partial time such as "in 30 minutes", "tomorrow at 9" or "Friday
    evening", so it can be turned into an absolute local time. Not needed
    when the user wants to travel now.
    """
    now = _now()
    return json.dumps(
        {"london_time": now.strftime("%Y-%m-%dT%H:%M"), "weekday": now.strftime("%A")}
    )
