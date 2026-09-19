"""Pure TFL line-status fetching/formatting logic.

Shared by the stdio MCP server (tfl.py) and the Azure Function App
(function_app/function_app.py, which gets its own copy of this file at
publish time -- see scripts/deploy-mcp-tools.sh).
"""

import json
import logging
from typing import Any
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

TFL_STATUS_BY_IDS = "https://api.tfl.gov.uk/Line/{ids}/Status"
TFL_STATUS_BY_MODE = "https://api.tfl.gov.uk/Line/Mode/{modes}/Status"
TFL_STOP_SEARCH = "https://api.tfl.gov.uk/StopPoint/Search"

LOOKUP_FAILURE_MESSAGE = json.dumps({"result": "Unable to fetch data from TFL."})
NO_STATIONS_MESSAGE = json.dumps({"result": "No matching stations found."})

DEFAULT_RAIL_MODES = ["tube", "dlr", "overground", "elizabeth-line"]


def make_tfl_request(url: str) -> dict[str, Any] | None:
    """Make a request to the TFL API. Returns None on any request failure."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        request_object = response.json()
    except requests.exceptions.RequestException as e:
        logger.debug("TFL request failed for %s: %s", url, e)
        return None
    logger.debug(request_object)
    return request_object


def fetch_line_status(line_ids: list[str]) -> list[dict] | None:
    """Fetch status for one or more lines in a single batched request."""
    url = TFL_STATUS_BY_IDS.format(ids=",".join(line_ids))
    return make_tfl_request(url)


def fetch_status_for_modes(modes: list[str]) -> list[dict] | None:
    """Fetch status for every line of the given modes in one request."""
    url = TFL_STATUS_BY_MODE.format(modes=",".join(modes))
    return make_tfl_request(url)


def filter_disrupted(lines: list[dict]) -> list[dict]:
    """Keep only lines with at least one non-"Good Service" status."""
    return [
        line
        for line in lines
        if any(
            status.get("statusSeverityDescription") != "Good Service"
            for status in line.get("lineStatuses", [])
        )
    ]


def format_status(lines: list[dict]) -> str:
    """Format line status as JSON, keyed by line id.

    Reads disruption detail (category, affected stops/routes) straight
    off each status entry's own nested "disruption" object -- TFL's
    separate Disruption endpoint returns no line-id field when queried
    with multiple ids, so it can't be attributed back to a line, and it
    has been observed to return nothing at all for lines that are
    genuinely disrupted per this same Status response.
    """
    result: dict[str, list[dict]] = {}
    for line in lines:
        statuses = []
        for status in line.get("lineStatuses", []):
            entry = {
                "status": status.get("statusSeverityDescription", "Unknown"),
                "reason": status.get("reason") or "No disruption",
            }
            disruption = status.get("disruption")
            if disruption:
                if disruption.get("category"):
                    entry["category"] = disruption["category"]
                if disruption.get("affectedStops"):
                    entry["affectedStops"] = disruption["affectedStops"]
                if disruption.get("affectedRoutes"):
                    entry["affectedRoutes"] = disruption["affectedRoutes"]
            statuses.append(entry)
        result[line["id"]] = statuses
    return json.dumps(result, indent=4)


def search_stations(
    query: str, modes: list[str], max_results: int = 5
) -> dict | None:
    """Search stations/stops by name, restricted to the given modes."""
    params = {
        "query": query,
        "modes": ",".join(modes),
        "maxResults": max_results,
    }
    url = f"{TFL_STOP_SEARCH}?{urlencode(params, safe=',')}"
    return make_tfl_request(url)


def format_stations(data: dict) -> str:
    """Format station matches as a JSON list of ids, name and modes.

    `id` is the stop id (valid for arrivals). `journey_id` is the ICS id
    TFL's journey planner accepts -- a hub's own `id` is not a valid
    journey endpoint -- falling back to `id` where no ICS id is given.
    """
    matches = data.get("matches", [])
    if not matches:
        return NO_STATIONS_MESSAGE
    return json.dumps(
        [
            {
                "id": m["id"],
                "journey_id": m.get("icsId") or m["id"],
                "name": m["name"],
                "modes": m.get("modes", []),
            }
            for m in matches
        ],
        indent=4,
    )
