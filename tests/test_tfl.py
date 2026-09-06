import json

import pandas as pd

import tfl


def test_get_tfl_status_calls_tfl_status_module(monkeypatch):
    def fake_fetch_all_tfl_status(lines, endpoint):
        assert lines == ["victoria"]
        return pd.DataFrame(
            [{"Line": "victoria", "statusSeverityDescription": "Good Service", "reason": None}]
        )

    monkeypatch.setattr(tfl.tfl_status, "fetch_all_tfl_status", fake_fetch_all_tfl_status)
    result = tfl.get_tfl_status(lines=["victoria"])
    assert "victoria" in result


def test_get_tfl_status_returns_error_message_when_empty(monkeypatch):
    def fake_fetch_all_tfl_status(lines, endpoint):
        return pd.DataFrame()

    monkeypatch.setattr(tfl.tfl_status, "fetch_all_tfl_status", fake_fetch_all_tfl_status)
    result = tfl.get_tfl_status(lines=["victoria"])
    assert json.loads(result) == {"result": "Unable to fetch TFL status."}
