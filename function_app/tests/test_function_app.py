import json

import function_app


def test_get_tfl_status_returns_formatted_json(monkeypatch):
    import pandas as pd

    def fake_fetch_all_tfl_status(lines, endpoint):
        assert lines == ["victoria"]
        return pd.DataFrame(
            [{"Line": "victoria", "statusSeverityDescription": "Good Service", "reason": None}]
        )

    monkeypatch.setattr(function_app.tfl_status, "fetch_all_tfl_status", fake_fetch_all_tfl_status)
    context = json.dumps({"arguments": {"lines": ["victoria"]}})
    result = function_app.get_tfl_status(context=context)
    assert "victoria" in result


def test_get_tfl_status_missing_lines_returns_error():
    context = json.dumps({"arguments": {}})
    result = function_app.get_tfl_status(context=context)
    assert json.loads(result) == {"error": "lines is required"}
