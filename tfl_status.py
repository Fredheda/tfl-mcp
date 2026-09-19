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
TFL_ARRIVALS = "https://api.tfl.gov.uk/StopPoint/{stop_id}/Arrivals"
TFL_STOP_POINT = "https://api.tfl.gov.uk/StopPoint/{stop_id}"

ARRIVALS_LIMIT = 8
NO_ARRIVALS_MESSAGE = json.dumps({"result": "No upcoming arrivals."})

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


def resolve_arrival_stops(stop_id: str) -> list[str] | None:
    """Stop ids that carry live predictions for a station id.

    A hub id (HUB...) has no predictions of its own -- only its child
    stops do -- so expand it to the children served by a TFL rail mode
    (National Rail-only and bus children have no TFL predictions worth
    fetching). Any other id is returned as-is. None on request failure.
    """
    if not stop_id.startswith("HUB"):
        return [stop_id]
    hub = make_tfl_request(TFL_STOP_POINT.format(stop_id=stop_id))
    if hub is None:
        return None
    return [
        child["id"]
        for child in hub.get("children", [])
        if set(child.get("modes", [])) & set(DEFAULT_RAIL_MODES)
    ]


def fetch_arrivals(stop_id: str) -> list[dict] | None:
    """Fetch every predicted arrival at a station (unsorted, all lines).

    Accepts a hub id as well as a plain stop id; a hub is expanded to its
    child stops and their arrivals merged. None if any request fails.
    """
    stop_ids = resolve_arrival_stops(stop_id)
    if stop_ids is None:
        return None
    arrivals: list[dict] = []
    for child_id in stop_ids:
        data = make_tfl_request(TFL_ARRIVALS.format(stop_id=child_id))
        if data is None:
            return None
        arrivals.extend(data)
    return arrivals


def format_arrivals(
    arrivals: list[dict],
    line_ids: list[str] | None = None,
    limit: int = ARRIVALS_LIMIT,
) -> str:
    """Format the next arrivals, soonest first, optionally for given lines.

    TFL returns every prediction at the stop in arbitrary order, so this
    filters, sorts by time to station and truncates to keep the reply small.
    """
    if line_ids:
        wanted = {line_id.lower() for line_id in line_ids}
        arrivals = [a for a in arrivals if a.get("lineId") in wanted]
    upcoming = sorted(arrivals, key=lambda a: a.get("timeToStation", 0))[:limit]
    if not upcoming:
        return NO_ARRIVALS_MESSAGE
    return json.dumps(
        [
            {
                "line": a.get("lineName"),
                "platform": a.get("platformName"),
                "destination": a.get("destinationName"),
                "minutes": round(a.get("timeToStation", 0) / 60),
            }
            for a in upcoming
        ],
        indent=4,
    )
