import json

import tfl


def test_get_tfl_status_calls_fetch_line_status(monkeypatch):
    def fake_fetch_line_status(line_ids):
        assert line_ids == ["victoria"]
        return [{"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service"}]}]

    monkeypatch.setattr(tfl.tfl_status, "fetch_line_status", fake_fetch_line_status)
    result = tfl.get_tfl_status(lines=["victoria"])
    assert "victoria" in result


def test_get_tfl_status_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(tfl.tfl_status, "fetch_line_status", lambda line_ids: None)
    result = tfl.get_tfl_status(lines=["victoria"])
    assert json.loads(result) == {"result": "Unable to fetch TFL status."}


def test_get_tfl_status_returns_error_message_when_no_lines_given():
    result = tfl.get_tfl_status(lines=[])
    assert json.loads(result) == {"result": "Unable to fetch TFL status."}


def test_get_disrupted_lines_filters_out_good_service(monkeypatch):
    def fake_fetch_status_for_modes(modes):
        assert modes == tfl.tfl_status.DEFAULT_RAIL_MODES
        return [
            {"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service"}]},
            {"id": "central", "lineStatuses": [{"statusSeverityDescription": "Minor Delays", "reason": "delays"}]},
        ]

    monkeypatch.setattr(tfl.tfl_status, "fetch_status_for_modes", fake_fetch_status_for_modes)
    result = tfl.get_disrupted_lines()
    parsed = json.loads(result)
    assert "central" in parsed
    assert "victoria" not in parsed


def test_get_disrupted_lines_returns_clean_message_when_nothing_disrupted(monkeypatch):
    monkeypatch.setattr(
        tfl.tfl_status,
        "fetch_status_for_modes",
        lambda modes: [{"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service"}]}],
    )
    result = tfl.get_disrupted_lines()
    assert json.loads(result) == {"result": "No disruptions reported."}


def test_get_disrupted_lines_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(tfl.tfl_status, "fetch_status_for_modes", lambda modes: None)
    result = tfl.get_disrupted_lines()
    assert json.loads(result) == {"result": "Unable to fetch TFL status."}
