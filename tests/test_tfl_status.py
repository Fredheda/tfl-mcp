import json
from urllib.parse import parse_qs, urlparse

import pytest
import requests

import tfl_status


def test_make_tfl_request_returns_json_on_success(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"lineStatuses": [{"statusSeverityDescription": "Good Service"}]}]

    def fake_get(url, timeout):
        assert timeout == 10
        return FakeResponse()

    monkeypatch.setattr(tfl_status.requests, "get", fake_get)
    result = tfl_status.make_tfl_request("http://example.com")
    assert result[0]["lineStatuses"][0]["statusSeverityDescription"] == "Good Service"


def test_make_tfl_request_returns_none_on_request_exception(monkeypatch):
    def fake_get(url, timeout):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(tfl_status.requests, "get", fake_get)
    result = tfl_status.make_tfl_request("http://example.com")
    assert result is None


def test_fetch_line_status_batches_ids_into_one_request(monkeypatch):
    seen_urls = []

    def fake_make_tfl_request(url):
        seen_urls.append(url)
        return [{"id": "victoria", "lineStatuses": []}, {"id": "central", "lineStatuses": []}]

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    result = tfl_status.fetch_line_status(["victoria", "central"])
    assert seen_urls == ["https://api.tfl.gov.uk/Line/victoria,central/Status"]
    assert result == [{"id": "victoria", "lineStatuses": []}, {"id": "central", "lineStatuses": []}]


def test_fetch_line_status_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(tfl_status, "make_tfl_request", lambda url: None)
    assert tfl_status.fetch_line_status(["victoria"]) is None


def test_fetch_status_for_modes_batches_modes_into_one_request(monkeypatch):
    seen_urls = []

    def fake_make_tfl_request(url):
        seen_urls.append(url)
        return [{"id": "victoria", "lineStatuses": []}]

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    result = tfl_status.fetch_status_for_modes(["tube", "dlr"])
    assert seen_urls == ["https://api.tfl.gov.uk/Line/Mode/tube,dlr/Status"]
    assert result == [{"id": "victoria", "lineStatuses": []}]


def test_fetch_status_for_modes_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(tfl_status, "make_tfl_request", lambda url: None)
    assert tfl_status.fetch_status_for_modes(["tube"]) is None


def test_filter_disrupted_drops_good_service_lines():
    lines = [
        {"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service"}]},
        {"id": "central", "lineStatuses": [{"statusSeverityDescription": "Minor Delays"}]},
    ]
    result = tfl_status.filter_disrupted(lines)
    assert [line["id"] for line in result] == ["central"]


def test_filter_disrupted_returns_empty_list_when_all_good():
    lines = [{"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service"}]}]
    assert tfl_status.filter_disrupted(lines) == []


def test_format_status_basic_good_service():
    lines = [{"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service"}]}]
    result = json.loads(tfl_status.format_status(lines))
    assert result == {"victoria": [{"status": "Good Service", "reason": "No disruption"}]}


def test_format_status_defaults_missing_and_none_reason():
    lines = [
        {"id": "victoria", "lineStatuses": [{"statusSeverityDescription": "Good Service", "reason": None}]},
    ]
    result = json.loads(tfl_status.format_status(lines))
    assert result["victoria"][0]["reason"] == "No disruption"


def test_format_status_includes_category_and_omits_empty_lists():
    lines = [{
        "id": "central",
        "lineStatuses": [{
            "statusSeverityDescription": "Minor Delays",
            "reason": "Central Line: Minor delays between White City and Ealing Broadway.",
            "disruption": {
                "category": "RealTime",
                "affectedStops": [],
                "affectedRoutes": [],
            },
        }],
    }]
    result = json.loads(tfl_status.format_status(lines))
    entry = result["central"][0]
    assert entry["status"] == "Minor Delays"
    assert entry["category"] == "RealTime"
    assert "affectedStops" not in entry
    assert "affectedRoutes" not in entry


def test_format_status_includes_nonempty_affected_stops():
    lines = [{
        "id": "mildmay",
        "lineStatuses": [{
            "statusSeverityDescription": "Part Closure",
            "reason": "Mildmay line: closed between Highbury & Islington and Stratford.",
            "disruption": {
                "category": "PlannedWork",
                "affectedStops": [{"id": "940GZZLUHAI"}],
                "affectedRoutes": [],
            },
        }],
    }]
    result = json.loads(tfl_status.format_status(lines))
    assert result["mildmay"][0]["affectedStops"] == [{"id": "940GZZLUHAI"}]


def test_search_stations_builds_query_and_mode_params(monkeypatch):
    seen_urls = []

    def fake_make_tfl_request(url):
        seen_urls.append(url)
        return {"matches": []}

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    tfl_status.search_stations("kings cross", ["tube", "dlr"], max_results=3)
    parsed = urlparse(seen_urls[0])
    assert parsed.path == "/StopPoint/Search"
    assert parse_qs(parsed.query) == {
        "query": ["kings cross"],
        "modes": ["tube,dlr"],
        "maxResults": ["3"],
    }


def test_search_stations_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(tfl_status, "make_tfl_request", lambda url: None)
    assert tfl_status.search_stations("waterloo", ["tube"]) is None


def test_format_stations_lists_ids_name_and_modes_only():
    data = {
        "matches": [
            {
                "id": "HUBKGX",
                "icsId": "1000129",
                "name": "King's Cross & St Pancras International",
                "modes": ["tube", "national-rail"],
                "lat": 51.53,
                "lon": -0.12,
            }
        ]
    }
    result = json.loads(tfl_status.format_stations(data))
    assert result == [
        {
            "id": "HUBKGX",
            "journey_id": "1000129",
            "name": "King's Cross & St Pancras International",
            "modes": ["tube", "national-rail"],
        }
    ]


def test_format_stations_journey_id_falls_back_to_id_without_ics_id():
    data = {"matches": [{"id": "940GZZLUWLO", "name": "Waterloo Underground Station", "modes": ["tube"]}]}
    result = json.loads(tfl_status.format_stations(data))
    assert result[0]["journey_id"] == "940GZZLUWLO"


def test_format_stations_reports_no_matches():
    result = json.loads(tfl_status.format_stations({"matches": []}))
    assert result == {"result": "No matching stations found."}


def _arrival(line_id, line_name, seconds, platform="Platform 1", destination="Somewhere"):
    return {
        "lineId": line_id,
        "lineName": line_name,
        "platformName": platform,
        "destinationName": destination,
        "timeToStation": seconds,
    }


def test_fetch_arrivals_requests_the_stop_arrivals_endpoint(monkeypatch):
    seen_urls = []

    def fake_make_tfl_request(url):
        seen_urls.append(url)
        return []

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    tfl_status.fetch_arrivals("940GZZLUWLO")
    assert seen_urls == ["https://api.tfl.gov.uk/StopPoint/940GZZLUWLO/Arrivals"]


def test_fetch_arrivals_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(tfl_status, "make_tfl_request", lambda url: None)
    assert tfl_status.fetch_arrivals("940GZZLUWLO") is None


def test_fetch_arrivals_expands_a_hub_to_its_tfl_rail_children(monkeypatch):
    seen_urls = []
    hub = {
        "id": "HUBKGX",
        "children": [
            {"id": "490G00005909", "modes": ["bus"]},
            {"id": "910GKNGX", "modes": ["national-rail"]},
            {"id": "940GZZLUKSX", "modes": ["tube"]},
            {"id": "910GHGHI", "modes": ["overground", "national-rail"]},
        ],
    }

    def fake_make_tfl_request(url):
        seen_urls.append(url)
        if url.endswith("/StopPoint/HUBKGX"):
            return hub
        return [{"lineId": "victoria", "timeToStation": 60}]

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    result = tfl_status.fetch_arrivals("HUBKGX")
    assert seen_urls == [
        "https://api.tfl.gov.uk/StopPoint/HUBKGX",
        "https://api.tfl.gov.uk/StopPoint/940GZZLUKSX/Arrivals",
        "https://api.tfl.gov.uk/StopPoint/910GHGHI/Arrivals",
    ]
    assert len(result) == 2


def test_fetch_arrivals_returns_none_when_hub_lookup_fails(monkeypatch):
    monkeypatch.setattr(tfl_status, "make_tfl_request", lambda url: None)
    assert tfl_status.fetch_arrivals("HUBKGX") is None


def test_fetch_arrivals_returns_none_when_a_child_lookup_fails(monkeypatch):
    def fake_make_tfl_request(url):
        if url.endswith("/StopPoint/HUBKGX"):
            return {"id": "HUBKGX", "children": [{"id": "940GZZLUKSX", "modes": ["tube"]}]}
        return None

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    assert tfl_status.fetch_arrivals("HUBKGX") is None


def test_fetch_arrivals_returns_empty_for_a_hub_without_tfl_rail_children(monkeypatch):
    hub = {"id": "HUBXXX", "children": [{"id": "910GXXXX", "modes": ["national-rail"]}]}
    monkeypatch.setattr(tfl_status, "make_tfl_request", lambda url: hub)
    assert tfl_status.fetch_arrivals("HUBXXX") == []


def test_journey_params_defaults_to_least_time_and_no_time_params():
    params = tfl_status.journey_params("leasttime", False, None, "departing")
    assert params == {"journeyPreference": "LeastTime"}


def test_journey_params_maps_preference_case_insensitively():
    params = tfl_status.journey_params("LeastInterchange", False, None, "departing")
    assert params["journeyPreference"] == "LeastInterchange"


def test_journey_params_adds_step_free_preference():
    params = tfl_status.journey_params("leasttime", True, None, "departing")
    assert params["accessibilityPreference"] == "StepFreeToVehicle,StepFreeToPlatform"


def test_journey_params_converts_when_to_tfl_date_time_and_direction():
    params = tfl_status.journey_params("leasttime", False, "2026-09-21T09:05", "arriving")
    assert params["date"] == "20260921"
    assert params["time"] == "0905"
    assert params["timeIs"] == "Arriving"


def test_journey_params_rejects_unknown_preference():
    with pytest.raises(ValueError, match="preference must be one of"):
        tfl_status.journey_params("fastest", False, None, "departing")


def test_journey_params_rejects_unknown_when_is():
    with pytest.raises(ValueError, match="when_is must be one of"):
        tfl_status.journey_params("leasttime", False, "2026-09-21T09:00", "sometime")


def test_journey_params_rejects_unparseable_when():
    with pytest.raises(ValueError, match="ISO local London time"):
        tfl_status.journey_params("leasttime", False, "tomorrow", "departing")


def test_journey_params_rejects_when_with_utc_offset():
    with pytest.raises(ValueError, match="without a UTC offset"):
        tfl_status.journey_params("leasttime", False, "2026-09-21T09:00+01:00", "departing")


def _journey_response():
    return {
        "journeys": [
            {
                "startDateTime": "2026-09-21T08:40:00",
                "arrivalDateTime": "2026-09-21T08:54:00",
                "duration": 14,
                "legs": [
                    {
                        "mode": {"id": "walking"},
                        "duration": 3,
                        "departurePoint": {"commonName": "Waterloo Underground Station"},
                        "arrivalPoint": {"commonName": "Waterloo Station"},
                        "routeOptions": [{"name": ""}],
                        "disruptions": [],
                    },
                    {
                        "mode": {"id": "tube"},
                        "duration": 11,
                        "departurePoint": {"commonName": "Waterloo Underground Station"},
                        "arrivalPoint": {"commonName": "King's Cross St. Pancras Underground Station"},
                        "routeOptions": [{"name": "Northern"}],
                        "disruptions": [
                            {"description": "Northern line: minor delays."},
                            {"description": ""},
                        ],
                    },
                ],
            }
        ]
    }


def test_fetch_journey_builds_url_from_ids_and_params(monkeypatch):
    seen_urls = []

    def fake_make_tfl_request(url):
        seen_urls.append(url)
        return {"journeys": []}

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    tfl_status.fetch_journey(
        "940GZZLUWLO", "1000129", "leastinterchange", True, "2026-09-21T09:00", "arriving"
    )
    parsed = urlparse(seen_urls[0])
    assert parsed.path == "/Journey/JourneyResults/940GZZLUWLO/to/1000129"
    assert parse_qs(parsed.query) == {
        "journeyPreference": ["LeastInterchange"],
        "accessibilityPreference": ["StepFreeToVehicle,StepFreeToPlatform"],
        "date": ["20260921"],
        "time": ["0900"],
        "timeIs": ["Arriving"],
    }


def test_fetch_journey_keeps_lat_lon_commas_in_path(monkeypatch):
    seen_urls = []
    monkeypatch.setattr(tfl_status, "make_tfl_request", lambda url: seen_urls.append(url) or {})
    tfl_status.fetch_journey("51.5,-0.12", "940GZZLUKSX")
    assert "/JourneyResults/51.5,-0.12/to/940GZZLUKSX" in seen_urls[0]


def test_fetch_journey_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(tfl_status, "make_tfl_request", lambda url: None)
    assert tfl_status.fetch_journey("940GZZLUWLO", "940GZZLUKSX") is None


def test_fetch_journey_raises_value_error_on_bad_when():
    with pytest.raises(ValueError):
        tfl_status.fetch_journey("a", "b", when="tomorrow")


def test_format_journeys_summarises_legs_and_omits_empty_fields():
    result = json.loads(tfl_status.format_journeys(_journey_response()))
    assert result[0]["minutes"] == 14
    assert result[0]["depart"] == "2026-09-21T08:40:00"
    assert result[0]["arrive"] == "2026-09-21T08:54:00"
    walk, tube = result[0]["legs"]
    assert walk == {
        "mode": "walking",
        "from": "Waterloo Underground Station",
        "to": "Waterloo Station",
        "minutes": 3,
    }
    assert tube["line"] == "Northern"
    assert tube["disruptions"] == ["Northern line: minor delays."]


def test_format_journeys_truncates_long_disruption_text():
    response = _journey_response()
    response["journeys"][0]["legs"][1]["disruptions"] = [{"description": "x" * 500}]
    tube = json.loads(tfl_status.format_journeys(response))[0]["legs"][1]
    [text] = tube["disruptions"]
    assert len(text) == 300
    assert text.endswith("…")


def test_format_journeys_drops_duplicate_disruptions_and_caps_per_leg():
    response = _journey_response()
    response["journeys"][0]["legs"][1]["disruptions"] = [
        {"description": "a"},
        {"description": "a"},
        {"description": "b"},
        {"description": "c"},
    ]
    tube = json.loads(tfl_status.format_journeys(response))[0]["legs"][1]
    assert tube["disruptions"] == ["a", "b"]


def test_format_journeys_limits_number_of_options():
    response = {"journeys": _journey_response()["journeys"] * 5}
    assert len(json.loads(tfl_status.format_journeys(response))) == 3


def test_format_journeys_reports_ambiguous_locations():
    disambiguation = {"fromLocationDisambiguation": {"matchStatus": "list"}}
    result = json.loads(tfl_status.format_journeys(disambiguation))
    assert "find_station" in result["result"]


def test_format_arrivals_sorts_soonest_first_and_converts_to_minutes():
    arrivals = [
        _arrival("northern", "Northern", 600, destination="Edgware"),
        _arrival("bakerloo", "Bakerloo", 120, destination="Harrow & Wealdstone"),
    ]
    result = json.loads(tfl_status.format_arrivals(arrivals))
    assert [a["line"] for a in result] == ["Bakerloo", "Northern"]
    assert result[0] == {
        "line": "Bakerloo",
        "platform": "Platform 1",
        "destination": "Harrow & Wealdstone",
        "minutes": 2,
    }


def test_format_arrivals_filters_by_line_ids():
    arrivals = [_arrival("northern", "Northern", 60), _arrival("bakerloo", "Bakerloo", 120)]
    result = json.loads(tfl_status.format_arrivals(arrivals, line_ids=["Bakerloo"]))
    assert [a["line"] for a in result] == ["Bakerloo"]


def test_format_arrivals_applies_limit():
    arrivals = [_arrival("northern", "Northern", s) for s in range(60, 60 * 20, 60)]
    result = json.loads(tfl_status.format_arrivals(arrivals, limit=3))
    assert len(result) == 3


def test_format_arrivals_reports_none_when_empty_or_filtered_out():
    assert json.loads(tfl_status.format_arrivals([])) == {"result": "No upcoming arrivals."}
    filtered = tfl_status.format_arrivals([_arrival("northern", "Northern", 60)], line_ids=["jubilee"])
    assert json.loads(filtered) == {"result": "No upcoming arrivals."}
