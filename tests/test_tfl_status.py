import json

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
