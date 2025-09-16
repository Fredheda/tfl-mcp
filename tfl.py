from typing import Any
from mcp.server.fastmcp import FastMCP
import requests
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
import logging

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("tfl")

TFL_ENDPOINT = "https://api.tfl.gov.uk/Line/{line}/Status"


def make_tfl_request(url: str) -> dict[str, Any] | None:
    """Make a request to the TFL API with proper error handling."""
    request_object = requests.get(url).json()
    logger.info(request_object)
    return request_object

        
def fetch_all_tfl_status(lines, endpoint):
    data = pd.DataFrame()
    logger.info(lines)
    for line in lines:
        logger.info(line)
        request_string = endpoint.format(line=line)
        request_object = make_tfl_request(request_string)
        temp_df = pd.DataFrame(request_object[0]["lineStatuses"])
        if "reason" not in temp_df.columns:
            temp_df["reason"] = "No Disruption"
        temp_df["Line"] = line
        data = pd.concat([data, temp_df])
    return data
    
def format_tfl_status(df: pd.DataFrame) -> str:
    output_data =  df[["Line","statusSeverityDescription","reason"]]

    output_data = output_data.reset_index(drop=True)

    output_data = output_data.fillna('No disruption')

    output_data['Status'] = output_data['statusSeverityDescription'] +": " + output_data['reason']
    output_data = output_data.drop(['statusSeverityDescription', 'reason'], axis= 1)

    grouped = output_data[["Line", "Status"]].groupby('Line', as_index=False).agg({'Status': ''.join})
    grouped = grouped.set_index('Line')

    json_response = grouped.to_json(indent=4)

    return json_response



@mcp.tool()
def get_tfl_status(lines: list[str]) -> str:
    """Get status for one or more tfl services.

    Args:
        lines: List of one or more TFL lines. Examples include: 'bakerloo', 'central', 'circle', 'district', 'dlr', 'hammersmith-city', 'jubilee', 'metropolitan',
    'northern','piccadilly','victoria', 'waterloo-city'
    """
    data = fetch_all_tfl_status(lines=lines, endpoint=TFL_ENDPOINT)

    if data.empty:
        return json.dumps({"result": "Unable to fetch TFL status."})

    status_overview = format_tfl_status(data)
    return status_overview

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')