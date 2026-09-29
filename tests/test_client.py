import json

import pandas as pd
import pytest

from gtrends_api import TrendReq, TrendsError
from gtrends_api.client import _timeframe_input

ITEMS = [
    {
        "type": "term", "term": "coffee", "status": "ok",
        "timeline": [
            {"date": "2025-09-28", "value": 81, "isPartial": False},
            {"date": "2025-10-05", "value": 77, "isPartial": True},
        ],
        "regions": [{"geoCode": "US-CA", "geoName": "California", "value": 100}],
        "relatedQueriesTop": [{"rank": 1, "query": "coffee near me", "value": 100, "formattedValue": "100", "link": "x"}],
        "relatedQueriesRising": [{"rank": 1, "query": "coffee tariffs", "value": 5000, "formattedValue": "Breakout", "link": "y"}],
    },
    {
        "type": "term", "term": "tea", "status": "ok",
        "timeline": [
            {"date": "2025-09-28", "value": 40, "isPartial": False},
            {"date": "2025-10-05", "value": 42, "isPartial": True},
        ],
        "regions": [{"geoCode": "US-CA", "geoName": "California", "value": 55}],
        "relatedQueriesTop": [],
        "relatedQueriesRising": [],
    },
]


class FakeResponse:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, json.dumps(data)

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, data, status=200):
        self.data, self.status, self.calls = data, status, []

    def post(self, url, params=None, json=None, timeout=None):
        self.calls.append(json)
        return FakeResponse(self.data, self.status)


def make(data=ITEMS, status=200):
    s = FakeSession(data, status)
    t = TrendReq(apify_token="test", session=s)
    t.build_payload(["coffee", "tea"], timeframe="today 12-m", geo="US")
    return t, s


def test_interest_over_time_shape():
    t, s = make()
    df = t.interest_over_time()
    assert list(df.columns) == ["coffee", "tea", "isPartial"]
    assert df.loc["2025-09-28", "coffee"] == 81
    assert bool(df.iloc[-1]["isPartial"]) is True
    assert s.calls[0]["searchTerms"] == ["coffee", "tea"]
    assert s.calls[0]["timeRange"] == "today 12-m"
    assert s.calls[0]["interestOverTime"] is True


def test_results_are_cached():
    t, s = make()
    t.interest_over_time()
    t.interest_over_time()
    assert len(s.calls) == 1


def test_interest_by_region():
    t, s = make()
    df = t.interest_by_region(resolution="REGION", inc_geo_code=True)
    assert df.loc["California", "coffee"] == 100
    assert df.loc["California", "geoCode"] == "US-CA"
    assert s.calls[0]["regionResolution"] == "REGION"


def test_related_queries():
    t, _ = make()
    rq = t.related_queries()
    assert rq["coffee"]["top"].iloc[0]["query"] == "coffee near me"
    assert rq["coffee"]["rising"].iloc[0]["formattedValue"] == "Breakout"
    assert rq["tea"]["top"] is None


def test_custom_timeframe():
    assert _timeframe_input("2025-01-01 2025-12-31") == {"timeRange": "custom", "customTimeRange": "2025-01-01 2025-12-31"}
    with pytest.raises(ValueError):
        _timeframe_input("last week")


def test_errors():
    with pytest.raises(ValueError):
        TrendReq(apify_token="x").build_payload(["a", "b", "c", "d", "e", "f"])
    t, _ = make(data={"error": {"message": "bad token"}}, status=401)
    with pytest.raises(TrendsError):
        t.interest_over_time()
    t, _ = make(data=[{"type": "term", "term": "coffee", "status": "failed", "errors": ["blocked"]}])
    with pytest.raises(TrendsError):
        t.interest_over_time()


def test_missing_token(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(TrendsError):
        TrendReq()
