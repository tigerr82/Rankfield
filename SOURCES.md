# Data sources

Every external source Rankfield touches, its licence, and whether it permits
commercial redistribution. Update this file whenever a provider changes.

| Source | Used for | Licence | Commercial redistribution |
|---|---|---|---|
| [SEC EDGAR XBRL](https://data.sec.gov/) `companyfacts` | All fundamentals | US government work — **public domain** | **Yes.** No restriction. |
| [Nasdaq stock screener](https://api.nasdaq.com/api/screener/stocks) | Universe, sector, industry, market cap | No published grant | **No.** Derived values only. |
| [Yahoo Finance chart API](https://query1.finance.yahoo.com/v8/finance/chart/) | Split/dividend-adjusted closes, volume | No redistribution grant | **No — replace before monetizing.** |
| [Stooq CSV](https://stooq.com/q/d/l/) | Alternative price adapter (**currently blocked**) | No redistribution grant | **No.** |

## Notes

### SEC EDGAR is the strategic advantage
Fundamentals are the differentiated asset here, and they are public domain. There is
no licensing obstacle to charging for the scores derived from them. This is why EDGAR
is the primary source rather than a convenience wrapper over a vendor feed.

The pipeline uses `companyfacts` rather than the `frames` endpoint. `frames` returns
one fact per filer for a period and is far cheaper in requests, but it carries `accn`
without `filed`, and returns only the latest (possibly restated) value — so it cannot
honour the point-in-time rule. `companyfacts` carries `filed`, `accn` and `form` on
every fact. Cost: one request per company per run, throttled to under 10/second.

### Price data is the part that actually constrains monetization
Stooq and Yahoo are both fine for personal research and neither grants redistribution
rights. Serving prices from either to paying users is a licensing problem. Both price
adapters carry a comment at the top of the file marking them as personal-use sources
requiring replacement before commercial launch. The adapter interface
(`scripts/rankfield/providers/`) is the whole surface that has to change — swapping in
a commercially licensed feed (Polygon, Tiingo, EODHD) is a one-file change.

### Stooq is currently unusable from a script
As of 2026-09, `https://stooq.com/q/d/l/?s={ticker}.us&i=d` no longer returns CSV to a
script. It returns an HTML interstitial that runs a JavaScript proof-of-work challenge
and issues the CSV only after it is solved. That is a bot-detection mechanism, and this
project does not circumvent it. The adapter is kept and raises a clear error rather
than returning nothing, so a misconfiguration surfaces loudly instead of producing an
empty price column.

The brief ranked Stooq first and FMP's free tier second. FMP requires registration for
an API key and caps the free tier at 250 calls/day, which cannot cover ~2,300 tickers
in a single run — it would need the backfill spread across ten days, and a monthly
snapshot cannot be assembled from ten different days' worth of calls without
misdating the scoring price. Yahoo is therefore the default, with the licensing caveat
above stated rather than hidden.

### Regulatory note (non-technical)
Selling stock rankings or scores may carry regulatory implications depending on how the
product is positioned and where subscribers are located — the line between "information
tool" and "investment advice" is jurisdiction-specific. Worth a professional opinion
before taking payment.

### Name
A web search found no existing company using "Rankfield". That is not legal clearance:
verify with the USPTO and the Israeli trademark register before any public or
commercial launch. No trademark symbols are used anywhere in the product.
