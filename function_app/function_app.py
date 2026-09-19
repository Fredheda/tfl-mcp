import json

import azure.functions as func

import tfl_status

app = func.FunctionApp()

_GET_TFL_STATUS_PROPERTIES = json.dumps(
    [
        {
            "propertyName": "lines",
            "propertyType": "array",
            "description": "List of one or more TFL line ids, e.g. 'victoria', 'central', 'bakerloo'.",
            "isRequired": True,
        }
    ]
)


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_tfl_status",
    description="Get live status for one or more TFL lines.",
    tool_properties=_GET_TFL_STATUS_PROPERTIES,
)
def get_tfl_status(context: str) -> str:
    invocation = json.loads(context)
    lines = invocation["arguments"].get("lines")
    if not lines:
        return json.dumps({"error": "lines is required"})

    data = tfl_status.fetch_line_status(lines)
    if data is None:
        return json.dumps({"result": "Unable to fetch TFL status."})
    return tfl_status.format_status(data)


_GET_DISRUPTED_LINES_PROPERTIES = json.dumps(
    [
        {
            "propertyName": "modes",
            "propertyType": "array",
            "description": "TFL modes to check, e.g. 'tube', 'dlr', 'overground', 'elizabeth-line'. Defaults to all four rail modes if omitted.",
            "isRequired": False,
        }
    ]
)


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_disrupted_lines",
    description="Get all TFL rail lines currently experiencing disruption.",
    tool_properties=_GET_DISRUPTED_LINES_PROPERTIES,
)
def get_disrupted_lines(context: str) -> str:
    invocation = json.loads(context)
    modes = invocation["arguments"].get("modes") or tfl_status.DEFAULT_RAIL_MODES

    data = tfl_status.fetch_status_for_modes(modes)
    if data is None:
        return json.dumps({"result": "Unable to fetch TFL status."})
    disrupted = tfl_status.filter_disrupted(data)
    if not disrupted:
        return json.dumps({"result": "No disruptions reported."})
    return tfl_status.format_status(disrupted)


_FIND_STATION_PROPERTIES = json.dumps(
    [
        {
            "propertyName": "query",
            "propertyType": "string",
            "description": "Station or place name to search for, e.g. 'kings cross'.",
            "isRequired": True,
        },
        {
            "propertyName": "modes",
            "propertyType": "array",
            "description": "TFL modes to search, e.g. 'tube', 'dlr', 'overground', 'elizabeth-line', 'national-rail'. Defaults to the four rail modes (not national-rail) if omitted.",
            "isRequired": False,
        },
    ]
)


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="find_station",
    description="Find TFL stations by name. Returns an `id` (for get_arrivals) and a `journey_id` (for plan_journey) per match. Use this before either, since they need ids rather than names.",
    tool_properties=_FIND_STATION_PROPERTIES,
)
def find_station(context: str) -> str:
    args = json.loads(context)["arguments"]
    query = args.get("query")
    if not query:
        return json.dumps({"error": "query is required"})
    modes = args.get("modes") or tfl_status.DEFAULT_RAIL_MODES

    data = tfl_status.search_stations(query, modes)
    if data is None:
        return tfl_status.LOOKUP_FAILURE_MESSAGE
    return tfl_status.format_stations(data)


_GET_ARRIVALS_PROPERTIES = json.dumps(
    [
        {
            "propertyName": "stop_id",
            "propertyType": "string",
            "description": "Station `id` from find_station, e.g. '940GZZLUWLO'.",
            "isRequired": True,
        },
        {
            "propertyName": "line_ids",
            "propertyType": "array",
            "description": "Optional TFL line ids to restrict to, e.g. 'victoria'. Omit to see every line at the station.",
            "isRequired": False,
        },
    ]
)


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_arrivals",
    description="Get the next trains arriving at a station, soonest first.",
    tool_properties=_GET_ARRIVALS_PROPERTIES,
)
def get_arrivals(context: str) -> str:
    args = json.loads(context)["arguments"]
    stop_id = args.get("stop_id")
    if not stop_id:
        return json.dumps({"error": "stop_id is required"})

    data = tfl_status.fetch_arrivals(stop_id)
    if data is None:
        return tfl_status.LOOKUP_FAILURE_MESSAGE
    return tfl_status.format_arrivals(data, args.get("line_ids"))
