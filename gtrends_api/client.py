"""A pytrends-style Google Trends client that never hits 429 errors.

The heavy lifting (sessions, proxies, retries, cookies, captchas) runs on the
Google Trends Scraper on Apify: https://apify.com/egra_van/google-trends-reliable
This module only sends the request and turns the JSON into pandas DataFrames
shaped like the ones pytrends returns.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import requests

try:  # pandas is optional: without it you get plain Python structures
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

ACTOR_ID = "egra_van~google-trends-reliable"
API_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"

# pytrends timeframes that map 1:1 to the scraper's presets
PRESET_TIMEFRAMES = {
    "now 1-H", "now 4-H", "now 1-d", "now 7-d",
    "today 1-m", "today 3-m", "today 12-m", "today 5-y", "all",
}
GPROPS = {"": "", "images": "images", "news": "news", "froogle": "froogle", "youtube": "youtube"}
RESOLUTIONS = {"COUNTRY": "COUNTRY", "REGION": "REGION", "CITY": "CITY", "DMA": "DMA"}

# pytrends' trending_searches(pn=...) uses country names; map the common ones to ISO codes
PN_TO_GEO = {
    "united_states": "US", "united_kingdom": "GB", "india": "IN", "germany": "DE", "france": "FR",
    "canada": "CA", "australia": "AU", "brazil": "BR", "japan": "JP", "italy": "IT", "spain": "ES",
    "mexico": "MX", "netherlands": "NL", "romania": "RO", "poland": "PL", "ukraine": "UA",
}


class TrendsError(RuntimeError):
    """Raised when the API call fails or returns no usable data."""


class TrendReq:
    """Drop-in style replacement for ``pytrends.request.TrendReq``.

    >>> from gtrends_api import TrendReq
    >>> pytrends = TrendReq()                      # reads APIFY_TOKEN from the environment
    >>> pytrends.build_payload(["coffee", "tea"], timeframe="today 12-m", geo="US")
    >>> df = pytrends.interest_over_time()
    """

    def __init__(self, apify_token: Optional[str] = None, hl: str = "en-US", tz: int = 0,
                 timeout: int = 300, session: Optional[requests.Session] = None, **_ignored: Any):
        self.token = apify_token or os.environ.get("APIFY_TOKEN")
        if not self.token:
            raise TrendsError(
                "No Apify API token. Pass TrendReq(apify_token='...') or set the APIFY_TOKEN "
                "environment variable. Get a free token at https://console.apify.com/settings/integrations"
            )
        self.hl = hl
        self.tz = tz
        self.timeout = timeout
        self.session = session or requests.Session()
        self.kw_list: List[str] = []
        self._payload: Dict[str, Any] = {}
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    # ------------------------------------------------------------------ payload
    def build_payload(self, kw_list: List[str], cat: int = 0, timeframe: str = "today 5-y",
                      geo: str = "", gprop: str = "") -> None:
        if not kw_list or len(kw_list) > 5:
            raise ValueError("kw_list must contain 1 to 5 search terms (like on trends.google.com).")
        if gprop not in GPROPS:
            raise ValueError(f"gprop must be one of {sorted(GPROPS)}.")
        self.kw_list = list(kw_list)
        payload: Dict[str, Any] = {
            "searchTerms": self.kw_list,
            "geo": geo or "",
            "gprop": GPROPS[gprop],
            "language": self.hl,
            "timezoneOffset": self.tz,
        }
        payload.update(_timeframe_input(timeframe))
        if cat:
            payload["categoryId"] = int(cat)
        self._payload = payload
        self._cache = {}

    # ------------------------------------------------------------------ public API
    def interest_over_time(self):
        items = self._terms(interestOverTime=True)
        rows: Dict[str, Dict[str, Any]] = {}
        partial: Dict[str, bool] = {}
        for item in items:
            for point in item.get("timeline") or []:
                if point.get("date") is None:
                    continue
                rows.setdefault(point["date"], {})[item["term"]] = point.get("value")
                partial[point["date"]] = partial.get(point["date"], False) or bool(point.get("isPartial"))
        if pd is None:
            return {"rows": rows, "isPartial": partial}
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame.from_dict(rows, orient="index")
        df = df[[t for t in self.kw_list if t in df.columns]]
        df["isPartial"] = [partial.get(k, False) for k in df.index]
        df.index = pd.to_datetime(df.index, utc=any("T" in str(k) for k in df.index))
        df.index.name = "date"
        return df.sort_index()

    def interest_by_region(self, resolution: str = "COUNTRY", inc_low_vol: bool = False, inc_geo_code: bool = False):
        resolution = resolution.upper()
        if resolution not in RESOLUTIONS:
            raise ValueError(f"resolution must be one of {sorted(RESOLUTIONS)}.")
        items = self._terms(interestByRegion=True, regionResolution=resolution,
                            includeLowSearchVolumeRegions=bool(inc_low_vol))
        rows: Dict[str, Dict[str, Any]] = {}
        codes: Dict[str, str] = {}
        for item in items:
            for region in item.get("regions") or []:
                name = region.get("geoName")
                rows.setdefault(name, {})[item["term"]] = region.get("value")
                codes[name] = region.get("geoCode")
        if pd is None:
            return rows
        df = pd.DataFrame.from_dict(rows, orient="index")
        if df.empty:
            return df
        df.index.name = "geoName"
        df = df[[t for t in self.kw_list if t in df.columns]]
        if inc_geo_code:
            df.insert(0, "geoCode", [codes.get(i) for i in df.index])
        return df

    def related_queries(self):
        return self._related("relatedQueries", "relatedQueriesTop", "relatedQueriesRising", "query")

    def related_topics(self):
        return self._related("relatedTopics", "relatedTopicsTop", "relatedTopicsRising", "title")

    def trending_searches(self, pn: str = "united_states", hours: int = 24, max_items: int = 50):
        """Today's Trending Now searches. ``pn`` accepts a pytrends country name or an ISO code."""
        geo = PN_TO_GEO.get(pn.lower(), pn.upper())
        payload = {
            "searchTerms": [], "interestOverTime": False, "trendingNow": True, "trendingGeo": geo,
            "trendingSource": "trendingPage" if hours != 24 else "rss",
            "trendingHours": str(hours), "maxTrendingItems": int(max_items),
        }
        items = [i for i in self._call(payload) if i.get("type") == "trending"]
        if pd is None:
            return items
        return pd.DataFrame(items)

    def raw(self, **extra: Any) -> List[Dict[str, Any]]:
        """Full JSON items for the current payload (every field the scraper returns)."""
        return self._terms(**extra)

    # ------------------------------------------------------------------ internals
    def _related(self, flag: str, top_key: str, rising_key: str, label: str):
        items = self._terms(**{flag: True, "maxRelatedItems": 25})
        out: Dict[str, Dict[str, Any]] = {}
        for item in items:
            top = item.get(top_key) or []
            rising = item.get(rising_key) or []
            if pd is not None:
                cols = [label, "value", "formattedValue", "link"] + (["topicType"] if label == "title" else [])
                top = pd.DataFrame(top)[[c for c in cols if top and c in top[0]]] if top else None
                rising = pd.DataFrame(rising)[[c for c in cols if rising and c in rising[0]]] if rising else None
            out[item["term"]] = {"top": top, "rising": rising}
        return out

    def _terms(self, **flags: Any) -> List[Dict[str, Any]]:
        if not self._payload:
            raise TrendsError("Call build_payload(...) first.")
        payload = {"interestOverTime": False, **self._payload, **flags}
        items = [i for i in self._call(payload) if i.get("type", "term") == "term"]
        failed = [f"{i.get('term')}: {'; '.join(i.get('errors') or []) or i.get('status')}"
                  for i in items if i.get("status") == "failed"]
        if failed and len(failed) == len(items):
            raise TrendsError("Google Trends returned no data: " + " | ".join(failed))
        return items

    def _call(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        key = repr(sorted(payload.items(), key=lambda kv: kv[0]))
        if key in self._cache:
            return self._cache[key]
        try:
            res = self.session.post(API_URL, params={"token": self.token}, json=payload, timeout=self.timeout)
        except requests.RequestException as err:
            raise TrendsError(f"Could not reach the Apify API: {err}") from err
        if res.status_code >= 400:
            raise TrendsError(f"Apify API error {res.status_code}: {res.text[:300]}")
        data = res.json()
        if not isinstance(data, list):
            raise TrendsError(f"Unexpected response: {str(data)[:300]}")
        self._cache[key] = data
        return data


def _timeframe_input(timeframe: str) -> Dict[str, Any]:
    timeframe = (timeframe or "today 5-y").strip()
    if timeframe in PRESET_TIMEFRAMES:
        return {"timeRange": timeframe}
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}( ?T\d{2})? \d{4}-\d{2}-\d{2}( ?T\d{2})?", timeframe):
        return {"timeRange": "custom", "customTimeRange": timeframe}
    raise ValueError(
        f"Unsupported timeframe {timeframe!r}. Use a preset such as 'today 12-m' or 'now 7-d', "
        "or a date range like '2025-01-01 2025-12-31'."
    )
