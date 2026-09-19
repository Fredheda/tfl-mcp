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


def test_find_station_returns_formatted_json(monkeypatch):
    def fake_search_stations(query, modes):
        assert query == "waterloo"
        assert modes == function_app.tfl_status.DEFAULT_RAIL_MODES
        return {"matches": [{"id": "940GZZLUWLO", "name": "Waterloo Underground Station", "modes": ["tube"]}]}

    monkeypatch.setattr(function_app.tfl_status, "search_stations", fake_search_stations)
    context = json.dumps({"arguments": {"query": "waterloo"}})
    result = json.loads(function_app.find_station(context=context))
    assert result[0]["id"] == "940GZZLUWLO"


def test_find_station_missing_query_returns_error():
    context = json.dumps({"arguments": {}})
    result = function_app.find_station(context=context)
    assert json.loads(result) == {"error": "query is required"}


def test_find_station_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(function_app.tfl_status, "search_stations", lambda query, modes: None)
    context = json.dumps({"arguments": {"query": "waterloo"}})
    result = function_app.find_station(context=context)
    assert json.loads(result) == {"result": "Unable to fetch data from TFL."}


def test_get_arrivals_returns_formatted_json(monkeypatch):
    def fake_fetch_arrivals(stop_id):
        assert stop_id == "940GZZLUWLO"
        return [{"lineId": "bakerloo", "lineName": "Bakerloo", "platformName": "P1", "destinationName": "Harrow", "timeToStation": 120}]

    monkeypatch.setattr(function_app.tfl_status, "fetch_arrivals", fake_fetch_arrivals)
    context = json.dumps({"arguments": {"stop_id": "940GZZLUWLO"}})
    result = json.loads(function_app.get_arrivals(context=context))
    assert result[0]["minutes"] == 2


def test_get_arrivals_missing_stop_id_returns_error():
    context = json.dumps({"arguments": {}})
    result = function_app.get_arrivals(context=context)
    assert json.loads(result) == {"error": "stop_id is required"}


def test_get_arrivals_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(function_app.tfl_status, "fetch_arrivals", lambda stop_id: None)
    context = json.dumps({"arguments": {"stop_id": "940GZZLUWLO"}})
    result = function_app.get_arrivals(context=context)
    assert json.loads(result) == {"result": "Unable to fetch data from TFL."}
