import pandas as pd
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


def test_fetch_all_tfl_status_success(monkeypatch):
    def fake_make_tfl_request(url):
        return [{"lineStatuses": [{"statusSeverityDescription": "Good Service"}]}]

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    df = tfl_status.fetch_all_tfl_status(["victoria"], tfl_status.TFL_ENDPOINT)
    assert df.iloc[0]["Line"] == "victoria"
    assert df.iloc[0]["statusSeverityDescription"] == "Good Service"


def test_fetch_all_tfl_status_degrades_on_failed_line(monkeypatch):
    def fake_make_tfl_request(url):
        return None

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    df = tfl_status.fetch_all_tfl_status(["victoria"], tfl_status.TFL_ENDPOINT)
    assert df.iloc[0]["Line"] == "victoria"
    assert df.iloc[0]["statusSeverityDescription"] == "Unknown"
    assert "Unable to fetch" in df.iloc[0]["reason"]


def test_fetch_all_tfl_status_handles_multiple_lines(monkeypatch):
    def fake_make_tfl_request(url):
        if "victoria" in url:
            return [{"lineStatuses": [{"statusSeverityDescription": "Good Service"}]}]
        return None

    monkeypatch.setattr(tfl_status, "make_tfl_request", fake_make_tfl_request)
    df = tfl_status.fetch_all_tfl_status(["victoria", "central"], tfl_status.TFL_ENDPOINT)
    assert len(df) == 2
    assert set(df["Line"]) == {"victoria", "central"}


def test_format_tfl_status_shapes_json():
    df = pd.DataFrame([
        {"Line": "victoria", "statusSeverityDescription": "Good Service", "reason": None},
    ])
    result = tfl_status.format_tfl_status(df)
    assert "victoria" in result
    assert "Good Service" in result
