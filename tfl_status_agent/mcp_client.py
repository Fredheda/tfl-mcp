import os

from langchain_mcp_adapters.client import MultiServerMCPClient


def build_mcp_client() -> MultiServerMCPClient:
    function_app_url = os.environ["FUNCTION_APP_URL"].rstrip("/")
    mcp_key = os.getenv("FUNCTION_MCP_KEY", "")
    headers = {"x-functions-key": mcp_key} if mcp_key else {}
    return MultiServerMCPClient(
        {
            "tfl": {
                "transport": "streamable_http",
                "url": f"{function_app_url}/runtime/webhooks/mcp",
                "headers": headers,
            }
        }
    )


async def load_mcp_tools() -> list:
    client = build_mcp_client()
    return await client.get_tools()
