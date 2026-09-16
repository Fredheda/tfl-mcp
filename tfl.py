import json
import logging

from mcp.server.fastmcp import FastMCP

import tfl_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Initialize FastMCP server (pinned to mcp v1 -- see pyproject.toml)
mcp = FastMCP("tfl")

FAILURE_MESSAGE = json.dumps({"result": "Unable to fetch TFL status."})


@mcp.tool()
def get_tfl_status(lines: list[str]) -> str:
    """Get status for one or more tfl services.

    Args:
        lines: List of one or more TFL line ids. Examples include: 'bakerloo', 'central', 'circle', 'district', 'dlr', 'elizabeth-line', 'hammersmith-city', 'jubilee', 'liberty', 'lioness', 'metropolitan', 'mildmay', 'northern', 'piccadilly', 'suffragette', 'victoria', 'waterloo-city', 'weaver', 'windrush'.
    """
    if not lines:
        return FAILURE_MESSAGE
    data = tfl_status.fetch_line_status(lines)
    if data is None:
        return FAILURE_MESSAGE
    return tfl_status.format_status(data)


NO_DISRUPTIONS_MESSAGE = json.dumps({"result": "No disruptions reported."})


@mcp.tool()
def get_disrupted_lines(modes: list[str] = tfl_status.DEFAULT_RAIL_MODES) -> str:
    """Get all lines currently experiencing disruption (i.e. not Good Service).

    Use this for general questions like "how's the tube doing" or "which
    lines are disrupted" where no specific line was named -- it checks
    every line across the given modes in one call, so there's no need to
    ask the user which line they mean first.

    Args:
        modes: TFL modes to check. Defaults to all rail modes: 'tube',
    'dlr', 'overground', 'elizabeth-line'.
    """
    data = tfl_status.fetch_status_for_modes(modes)
    if data is None:
        return FAILURE_MESSAGE
    disrupted = tfl_status.filter_disrupted(data)
    if not disrupted:
        return NO_DISRUPTIONS_MESSAGE
    return tfl_status.format_status(disrupted)


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
