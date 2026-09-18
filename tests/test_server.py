import importlib


def test_agent_card_advertises_streaming(monkeypatch):
    # server.py validates these at import time; conftest already supplies
    # OPENAI_API_KEY. Neither is used for a network call here.
    monkeypatch.setenv("FUNCTION_APP_URL", "https://func.example.invalid")
    server = importlib.import_module("tfl_status_agent.server")

    assert server.agent_card.capabilities.streaming is True
