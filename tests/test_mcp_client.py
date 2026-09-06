import os

from tfl_status_agent.mcp_client import build_mcp_client


def test_build_mcp_client_uses_env_vars(monkeypatch):
    monkeypatch.setenv("FUNCTION_APP_URL", "https://func-tfl-mcp.azurewebsites.net")
    monkeypatch.setenv("FUNCTION_MCP_KEY", "test-key")

    client = build_mcp_client()

    config = client.connections["tfl"]
    assert config["url"] == "https://func-tfl-mcp.azurewebsites.net/runtime/webhooks/mcp"
    assert config["headers"] == {"x-functions-key": "test-key"}
    assert config["transport"] == "streamable_http"
