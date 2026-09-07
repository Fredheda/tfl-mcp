"""Pure TFL line-status fetching/formatting logic.

Shared by the stdio MCP server (tfl.py) and the Azure Function App
(function_app/function_app.py, which gets its own copy of this file at
publish time -- see scripts/deploy-mcp-tools.sh).
"""

import logging
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

TFL_ENDPOINT = "https://api.tfl.gov.uk/Line/{line}/Status"


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


def fetch_all_tfl_status(lines: list[str], endpoint: str) -> pd.DataFrame:
    frames = []
    logger.debug(lines)
    for line in lines:
        logger.debug(line)
        request_string = endpoint.format(line=line)
        request_object = make_tfl_request(request_string)
        if request_object is None:
            temp_df = pd.DataFrame(
                [
                    {
                        "statusSeverityDescription": "Unknown",
                        "reason": "Unable to fetch TFL status for this line.",
                    }
                ]
            )
        else:
            temp_df = pd.DataFrame(request_object[0]["lineStatuses"])
            if "reason" not in temp_df.columns:
                temp_df["reason"] = "No Disruption"
        temp_df["Line"] = line
        frames.append(temp_df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def format_tfl_status(df: pd.DataFrame) -> str:
    output_data = df[["Line", "statusSeverityDescription", "reason"]]
    output_data = output_data.reset_index(drop=True)
    output_data = output_data.fillna("No disruption")
    output_data["Status"] = (
        output_data["statusSeverityDescription"] + ": " + output_data["reason"]
    )
    output_data = output_data.drop(["statusSeverityDescription", "reason"], axis=1)
    grouped = output_data[["Line", "Status"]].groupby("Line", as_index=False).agg(
        {"Status": "".join}
    )
    grouped = grouped.set_index("Line")
    return grouped.to_json(indent=4)
