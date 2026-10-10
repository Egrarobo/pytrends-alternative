# pytrends alternative: Google Trends API for Python, with 429 retries handled remotely

**pytrends is archived and Google Trends blocks it with `429 Too Many Requests`.** Google's official Trends API is still in closed alpha. This small library gives you the same `TrendReq` interface as pytrends, but the requests run on a managed scraper: each request is paced and retried with a fresh Google session; if Google keeps refusing, it falls back to the embeddable chart pages and, last, to a real browser. Retries and time limits are fixed, so runs end instead of hanging. Google still refuses some requests. Terms that still fail are not billed.

```python
from gtrends_api import TrendReq   # was: from pytrends.request import TrendReq

pytrends = TrendReq()              # reads APIFY_TOKEN from the environment
pytrends.build_payload(["coffee", "tea"], timeframe="today 12-m", geo="US")

df = pytrends.interest_over_time()
print(df.tail())
```

Output of a real run on October 10, 2026 (about 30 seconds):

```
            coffee  tea  isPartial
date                              
2026-09-06      74   31      False
2026-09-13      74   31      False
2026-09-20      74   33      False
2026-09-27      70   31      False
2026-10-04      70   30       True
```

## Is there an official Google Trends API?

Yes, in closed alpha: Google opened applications on July 24, 2025 and, as of October 10, 2026, still admits "a limited set of developers" ([API page](https://developers.google.com/search/apis/trends)). If you're not in it, this library gives you the pytrends interface today. Other official options: the CSV download on the Google Trends site, the Google Trends BigQuery dataset and the Trending Now RSS feed.

## Why switch

| | pytrends | this library |
|---|---|---|
| `429 Too Many Requests` | Frequent, especially from servers and notebooks | Still happens; paced, retried with a new Google session, then the embeddable charts and a real browser |
| Maintained | Archived (read-only) since April 2025 | Maintained |
| Interface | `TrendReq`, `build_payload`, `interest_over_time`… | Same method names, same DataFrame shapes |
| Hundreds of keywords | Manual batching, not comparable between batches | Available via `raw()` with an anchor term on one scale |
| Cost | Free, but blocked | Pay per keyword: $0.003 per keyword (about $3 per 1,000) on Apify's Free and Starter plans, less on Scale ($2.20 per 1,000) and Business ($1.50 per 1,000). Each method call is billed separately (see [Pricing](#pricing)). Apify's free plan includes a small monthly credit, enough to try it |

## Install

```bash
pip install git+https://github.com/Egrarobo/pytrends-alternative.git
```

Get an API token: create a free account at [apify.com](https://apify.com), then copy the token from **Settings → API & Integrations**.

```bash
export APIFY_TOKEN="your-token"
```

## Supported methods

| pytrends method | Supported | Notes |
|---|---|---|
| `build_payload(kw_list, cat, timeframe, geo, gprop)` | Yes | 1–5 terms, like trends.google.com |
| `interest_over_time()` | Yes | DataFrame indexed by date, one column per term, plus `isPartial` |
| `interest_by_region(resolution, inc_low_vol, inc_geo_code)` | Yes | `COUNTRY`, `REGION`, `CITY`, `DMA` |
| `related_queries()` | Yes | `{term: {"top": DataFrame, "rising": DataFrame}}` |
| `related_topics()` | Yes | Same shape, with `title` and `topicType` |
| `trending_searches(pn)` | Yes | `pn="united_states"` or an ISO code like `"GB"` |
| `raw()` | New | Full JSON per term: averages, peak date, top region, explore link |

Timeframes: `now 1-H`, `now 4-H`, `now 1-d`, `now 7-d`, `today 1-m`, `today 3-m`, `today 12-m`, `today 5-y`, `all`, or a date range such as `2025-01-01 2025-12-31`.

## More examples

**Top US states for a keyword**

```python
pytrends.build_payload(["solar panels"], timeframe="today 12-m", geo="US")
states = pytrends.interest_by_region(resolution="REGION", inc_geo_code=True)
print(states.sort_values("solar panels", ascending=False).head(10))
```

**Rising related searches (content ideas)**

```python
pytrends.build_payload(["air fryer"], timeframe="today 3-m", geo="GB")
rising = pytrends.related_queries()["air fryer"]["rising"]
print(rising[["query", "formattedValue"]])
```

**Today's trending searches**

```python
print(pytrends.trending_searches(pn="united_kingdom")[["rank", "title", "approxTraffic"]])
```

**Many keywords on one scale** (more than 5 terms, comparable with each other): call the scraper directly with an anchor term, see the [scraper page](https://apify.com/egra_van/google-trends-reliable).

## Pricing

You pay Apify per keyword for which all requested data was collected:

| Apify plan | Price per keyword | Per 1,000 keywords |
|---|---|---|
| Free, Starter | $0.003 | $3.00 |
| Scale | $0.0022 | $2.20 |
| Business and higher | $0.0015 | $1.50 |

Plus a tiny start fee per run ($0.00005). Failed keywords are free.

**Each method call is a separate run on Apify and is billed per keyword.** For example, 2 keywords with `interest_over_time()`, `interest_by_region()` and `related_queries()` are billed as 6 keywords. To get the timeline, regions and related queries in one run, billed once per keyword, use:

```python
data = pytrends.raw(interestOverTime=True, interestByRegion=True, relatedQueries=True)
```

`raw()` returns the full JSON instead of DataFrames. Repeating the same method call with the same payload is cached and not billed again.

## No Python? Use it from anywhere

The same data is available without code: run the [Google Trends Scraper](https://apify.com/egra_van/google-trends-reliable) in the browser, schedule it, export to Excel or Google Sheets, or call it from Make, Zapier, n8n or any HTTP client.

## Notes

- Values are Google's relative 0–100 index, not search counts. That is how Google Trends works.
- You pay only for terms where all requested data was collected; failed terms are free.
- This project is not affiliated with Google or with the pytrends authors.

## License

MIT
