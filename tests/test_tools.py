import json
from datetime import datetime, timezone

from tfl_status_agent import tools


def test_get_current_time_reports_london_local_time_during_bst(monkeypatch):
    # 23:30 UTC on 1 July is 00:30 on 2 July in London (BST, UTC+1).
    fixed = datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc).astimezone(tools.LONDON)
    monkeypatch.setattr(tools, "_now", lambda: fixed)

    result = json.loads(tools.get_current_time.invoke({}))

    assert result == {"london_time": "2026-07-02T00:30", "weekday": "Thursday"}


def test_get_current_time_matches_utc_in_winter(monkeypatch):
    fixed = datetime(2026, 1, 15, 8, 5, tzinfo=timezone.utc).astimezone(tools.LONDON)
    monkeypatch.setattr(tools, "_now", lambda: fixed)

    result = json.loads(tools.get_current_time.invoke({}))

    assert result == {"london_time": "2026-01-15T08:05", "weekday": "Thursday"}
