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
