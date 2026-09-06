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


@mcp.tool()
def get_tfl_status(lines: list[str]) -> str:
    """Get status for one or more tfl services.

    Args:
        lines: List of one or more TFL lines. Examples include: 'bakerloo', 'central', 'circle', 'district', 'dlr', 'hammersmith-city', 'jubilee', 'metropolitan',
    'northern','piccadilly','victoria', 'waterloo-city'
    """
    data = tfl_status.fetch_all_tfl_status(lines=lines, endpoint=tfl_status.TFL_ENDPOINT)

    if data.empty:
        return json.dumps({"result": "Unable to fetch TFL status."})

    return tfl_status.format_tfl_status(data)


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
