import json

import pytest

import function_app


def test_get_tfl_status_returns_formatted_json(monkeypatch):
    def fake_fetch_line_status(line_ids):
        assert line_ids == ["victoria"]
        return [
            {
                "id": "victoria",
                "lineStatuses": [{"statusSeverityDescription": "Good Service"}],
            }
        ]

    monkeypatch.setattr(
        function_app.tfl_status, "fetch_line_status", fake_fetch_line_status
    )
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
        return [
            {
                "id": "central",
                "lineStatuses": [
                    {"statusSeverityDescription": "Minor Delays", "reason": "delays"}
                ],
            }
        ]

    monkeypatch.setattr(
        function_app.tfl_status, "fetch_status_for_modes", fake_fetch_status_for_modes
    )
    context = json.dumps({"arguments": {}})
    result = function_app.get_disrupted_lines(context=context)
    assert "central" in result


def test_get_disrupted_lines_returns_clean_message_when_nothing_disrupted(monkeypatch):
    monkeypatch.setattr(
        function_app.tfl_status,
        "fetch_status_for_modes",
        lambda modes: [
            {
                "id": "victoria",
                "lineStatuses": [{"statusSeverityDescription": "Good Service"}],
            }
        ],
    )
    context = json.dumps({"arguments": {}})
    result = function_app.get_disrupted_lines(context=context)
    assert json.loads(result) == {"result": "No disruptions reported."}


def test_find_station_returns_formatted_json(monkeypatch):
    def fake_search_stations(query, modes):
        assert query == "waterloo"
        assert modes == function_app.tfl_status.DEFAULT_RAIL_MODES
        return {
            "matches": [
                {
                    "id": "940GZZLUWLO",
                    "name": "Waterloo Underground Station",
                    "modes": ["tube"],
                }
            ]
        }

    monkeypatch.setattr(
        function_app.tfl_status, "search_stations", fake_search_stations
    )
    context = json.dumps({"arguments": {"query": "waterloo"}})
    result = json.loads(function_app.find_station(context=context))
    assert result[0]["id"] == "940GZZLUWLO"


def test_find_station_missing_query_returns_error():
    context = json.dumps({"arguments": {}})
    result = function_app.find_station(context=context)
    assert json.loads(result) == {"error": "query is required"}


def test_find_station_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(
        function_app.tfl_status, "search_stations", lambda query, modes: None
    )
    context = json.dumps({"arguments": {"query": "waterloo"}})
    result = function_app.find_station(context=context)
    assert json.loads(result) == {"result": "Unable to fetch data from TFL."}


def test_get_arrivals_returns_formatted_json(monkeypatch):
    def fake_fetch_arrivals(stop_id):
        assert stop_id == "940GZZLUWLO"
        return [
            {
                "lineId": "bakerloo",
                "lineName": "Bakerloo",
                "platformName": "P1",
                "destinationName": "Harrow",
                "timeToStation": 120,
            }
        ]

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


def test_plan_journey_returns_formatted_json(monkeypatch):
    def fake_fetch_journey(origin, destination, preference, step_free, when, when_is):
        assert (origin, destination) == ("940GZZLUWLO", "1000129")
        assert preference == "leasttime"
        assert step_free is False
        assert when is None
        assert when_is == "departing"
        return {
            "journeys": [
                {
                    "startDateTime": "s",
                    "arrivalDateTime": "a",
                    "duration": 14,
                    "legs": [],
                }
            ]
        }

    monkeypatch.setattr(function_app.tfl_status, "fetch_journey", fake_fetch_journey)
    context = json.dumps(
        {"arguments": {"origin": "940GZZLUWLO", "destination": "1000129"}}
    )
    result = json.loads(function_app.plan_journey(context=context))
    assert result[0]["minutes"] == 14


def test_plan_journey_passes_optional_arguments(monkeypatch):
    seen = {}

    def fake_fetch_journey(origin, destination, preference, step_free, when, when_is):
        seen.update(
            preference=preference, step_free=step_free, when=when, when_is=when_is
        )
        return {"journeys": []}

    monkeypatch.setattr(function_app.tfl_status, "fetch_journey", fake_fetch_journey)
    context = json.dumps(
        {
            "arguments": {
                "origin": "a",
                "destination": "b",
                "preference": "leastwalking",
                "step_free": True,
                "when": "2026-09-21T09:00",
                "when_is": "arriving",
            }
        }
    )
    function_app.plan_journey(context=context)
    assert seen == {
        "preference": "leastwalking",
        "step_free": True,
        "when": "2026-09-21T09:00",
        "when_is": "arriving",
    }


def test_plan_journey_missing_origin_or_destination_returns_error():
    context = json.dumps({"arguments": {"origin": "a"}})
    result = function_app.plan_journey(context=context)
    assert json.loads(result) == {"error": "origin and destination are required"}


def test_plan_journey_reports_bad_when_as_a_result():
    context = json.dumps(
        {"arguments": {"origin": "a", "destination": "b", "when": "tomorrow"}}
    )
    result = json.loads(function_app.plan_journey(context=context))
    assert "ISO local London time" in result["result"]


def test_plan_journey_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(
        function_app.tfl_status, "fetch_journey", lambda *args, **kwargs: None
    )
    context = json.dumps({"arguments": {"origin": "a", "destination": "b"}})
    result = function_app.plan_journey(context=context)
    assert json.loads(result) == {"result": "Unable to fetch data from TFL."}


def _fail_if_called(*args, **kwargs):
    raise AssertionError("TFL must not be called with invalid arguments")


@pytest.mark.parametrize("bad", ["victoria", [1], ["victoria", 2], {"a": 1}, 7])
def test_get_tfl_status_rejects_lines_that_are_not_a_list_of_strings(monkeypatch, bad):
    monkeypatch.setattr(function_app.tfl_status, "fetch_line_status", _fail_if_called)
    context = json.dumps({"arguments": {"lines": bad}})
    result = function_app.get_tfl_status(context=context)
    assert json.loads(result) == {"error": "lines must be a list of strings"}


@pytest.mark.parametrize("bad", ["tube", [1], ["tube", None]])
def test_get_disrupted_lines_rejects_modes_that_are_not_a_list_of_strings(
    monkeypatch, bad
):
    monkeypatch.setattr(
        function_app.tfl_status, "fetch_status_for_modes", _fail_if_called
    )
    context = json.dumps({"arguments": {"modes": bad}})
    result = function_app.get_disrupted_lines(context=context)
    assert json.loads(result) == {"error": "modes must be a list of strings"}


@pytest.mark.parametrize("bad", ["tube", [1]])
def test_find_station_rejects_modes_that_are_not_a_list_of_strings(monkeypatch, bad):
    monkeypatch.setattr(function_app.tfl_status, "search_stations", _fail_if_called)
    context = json.dumps({"arguments": {"query": "kings cross", "modes": bad}})
    result = function_app.find_station(context=context)
    assert json.loads(result) == {"error": "modes must be a list of strings"}


def test_find_station_rejects_a_query_that_is_not_a_string(monkeypatch):
    monkeypatch.setattr(function_app.tfl_status, "search_stations", _fail_if_called)
    context = json.dumps({"arguments": {"query": 123}})
    result = function_app.find_station(context=context)
    assert json.loads(result) == {"error": "query must be a string"}


def test_get_arrivals_rejects_a_stop_id_that_is_not_a_string(monkeypatch):
    monkeypatch.setattr(function_app.tfl_status, "fetch_arrivals", _fail_if_called)
    context = json.dumps({"arguments": {"stop_id": 123}})
    result = function_app.get_arrivals(context=context)
    assert json.loads(result) == {"error": "stop_id must be a string"}


@pytest.mark.parametrize("bad", ["victoria", [1]])
def test_get_arrivals_rejects_line_ids_that_are_not_a_list_of_strings(monkeypatch, bad):
    monkeypatch.setattr(function_app.tfl_status, "fetch_arrivals", _fail_if_called)
    context = json.dumps({"arguments": {"stop_id": "940GZZLUWLO", "line_ids": bad}})
    result = function_app.get_arrivals(context=context)
    assert json.loads(result) == {"error": "line_ids must be a list of strings"}


@pytest.mark.parametrize("field", ["origin", "destination"])
def test_plan_journey_rejects_a_location_that_is_not_a_string(monkeypatch, field):
    monkeypatch.setattr(function_app.tfl_status, "fetch_journey", _fail_if_called)
    arguments = {"origin": "a", "destination": "b", field: 5}
    result = function_app.plan_journey(context=json.dumps({"arguments": arguments}))
    assert json.loads(result) == {"error": "origin and destination must be strings"}
