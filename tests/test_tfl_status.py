import json
from urllib.parse import parse_qs, urlparse

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
