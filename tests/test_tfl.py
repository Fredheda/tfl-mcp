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


def test_find_station_calls_search_stations(monkeypatch):
    def fake_search_stations(query, modes):
        assert query == "waterloo"
        assert modes == tfl.tfl_status.DEFAULT_RAIL_MODES
        return {"matches": [{"id": "940GZZLUWLO", "name": "Waterloo Underground Station", "modes": ["tube"]}]}

    monkeypatch.setattr(tfl.tfl_status, "search_stations", fake_search_stations)
    result = json.loads(tfl.find_station(query="waterloo"))
    assert result[0]["id"] == "940GZZLUWLO"


def test_find_station_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(tfl.tfl_status, "search_stations", lambda query, modes: None)
    result = tfl.find_station(query="waterloo")
    assert json.loads(result) == {"result": "Unable to fetch data from TFL."}


def test_get_arrivals_passes_stop_id_and_line_filter(monkeypatch):
    def fake_fetch_arrivals(stop_id):
        assert stop_id == "940GZZLUWLO"
        return [
            {"lineId": "bakerloo", "lineName": "Bakerloo", "platformName": "P1", "destinationName": "Harrow", "timeToStation": 120},
            {"lineId": "northern", "lineName": "Northern", "platformName": "P2", "destinationName": "Edgware", "timeToStation": 60},
        ]

    monkeypatch.setattr(tfl.tfl_status, "fetch_arrivals", fake_fetch_arrivals)
    result = json.loads(tfl.get_arrivals(stop_id="940GZZLUWLO", line_ids=["bakerloo"]))
    assert [a["line"] for a in result] == ["Bakerloo"]


def test_get_arrivals_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(tfl.tfl_status, "fetch_arrivals", lambda stop_id: None)
    result = tfl.get_arrivals(stop_id="940GZZLUWLO")
    assert json.loads(result) == {"result": "Unable to fetch data from TFL."}


def test_plan_journey_passes_arguments_through(monkeypatch):
    def fake_fetch_journey(origin, destination, preference, step_free, when, when_is):
        assert (origin, destination) == ("940GZZLUWLO", "1000129")
        assert preference == "leastinterchange"
        assert step_free is True
        assert when == "2026-09-21T09:00"
        assert when_is == "arriving"
        return {"journeys": [{"startDateTime": "s", "arrivalDateTime": "a", "duration": 14, "legs": []}]}

    monkeypatch.setattr(tfl.tfl_status, "fetch_journey", fake_fetch_journey)
    result = json.loads(
        tfl.plan_journey(
            origin="940GZZLUWLO",
            destination="1000129",
            preference="leastinterchange",
            step_free=True,
            when="2026-09-21T09:00",
            when_is="arriving",
        )
    )
    assert result[0]["minutes"] == 14


def test_plan_journey_returns_error_message_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(
        tfl.tfl_status, "fetch_journey", lambda *args, **kwargs: None
    )
    result = tfl.plan_journey(origin="a", destination="b")
    assert json.loads(result) == {"result": "Unable to fetch data from TFL."}


def test_plan_journey_reports_bad_when_as_a_result_not_an_exception():
    result = json.loads(tfl.plan_journey(origin="a", destination="b", when="tomorrow"))
    assert "ISO local London time" in result["result"]
