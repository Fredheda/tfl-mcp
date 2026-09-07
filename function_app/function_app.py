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
    description="Get live status for one or more London Underground/DLR lines.",
    tool_properties=_GET_TFL_STATUS_PROPERTIES,
)
def get_tfl_status(context: str) -> str:
    invocation = json.loads(context)
    lines = invocation["arguments"].get("lines")
    if not lines:
        return json.dumps({"error": "lines is required"})

    data = tfl_status.fetch_all_tfl_status(lines=lines, endpoint=tfl_status.TFL_ENDPOINT)
    if data.empty:
        return json.dumps({"result": "Unable to fetch TFL status."})
    return tfl_status.format_tfl_status(data)
