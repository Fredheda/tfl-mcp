import json

import function_app


def test_get_tfl_status_returns_formatted_json(monkeypatch):
    def fake_fetch_line_status(line_ids):
        assert line_ids == ["victoria"]
        return [{"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service"}]}]

    monkeypatch.setattr(function_app.tfl_status, "fetch_line_status", fake_fetch_line_status)
    context = json.dumps({"arguments": {"lines": ["victoria"]}})
    result = function_app.get_tfl_status(context=context)
    assert "victoria" in result


def test_get_tfl_status_missing_lines_returns_error():
    context = json.dumps({"arguments": {}})
    result = function_app.get_tfl_status(context=context)
    assert json.loads(result) == {"error": "lines is required"}


def test_get_disrupted_lines_returns_formatted_json(monkeypatch):
    def fake_fetch_status_for_modes(modes):
        assert modes == function_app.tfl_status.DEFAULT_RAIL_MODES
        return [{"id": "central", "lineStatuses": [{"statusSeverityDescription": "Minor Delays", "reason": "delays"}]}]

    monkeypatch.setattr(function_app.tfl_status, "fetch_status_for_modes", fake_fetch_status_for_modes)
    context = json.dumps({"arguments": {}})
    result = function_app.get_disrupted_lines(context=context)
    assert "central" in result


def test_get_disrupted_lines_returns_clean_message_when_nothing_disrupted(monkeypatch):
    monkeypatch.setattr(
        function_app.tfl_status,
        "fetch_status_for_modes",
        lambda modes: [{"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service"}]}],
    )
    context = json.dumps({"arguments": {}})
    result = function_app.get_disrupted_lines(context=context)
    assert json.loads(result) == {"result": "No disruptions reported."}
