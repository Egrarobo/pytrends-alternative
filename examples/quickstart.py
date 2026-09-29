"""Run: APIFY_TOKEN=... python examples/quickstart.py"""
from gtrends_api import TrendReq

pytrends = TrendReq()
pytrends.build_payload(["coffee", "tea", "energy drink"], timeframe="today 12-m", geo="US")
print(pytrends.interest_over_time().tail())
print(pytrends.interest_by_region(resolution="REGION").head())
for term, lists in pytrends.related_queries().items():
    print(term, lists["rising"].head() if lists["rising"] is not None else "no rising queries")
