# Rankfield

**Sector-relative equity scoring, with the work shown.**

Live: <https://tigerr82.github.io/Rankfield/>

Rankfield ranks every NYSE and NASDAQ common stock above $1B market cap on a transparent,
sector-relative composite score, and shows every sub-score behind every score. A scheduled
batch job produces static JSON; the website only ever reads those files. No live data, no
runtime API calls, no server, no database — and no recurring cost.

---

## What the first real run produced

| | |
|---|---|
| Listed on NYSE/NASDAQ | 6,856 |
| Common stock, above $1B, one line per company | 2,266 |
| Scored | **1,354** (1,177 operating · 154 financials & REITs · 23 pre-revenue) |
| Routed to *Insufficient data* | 498 |
| Metric coverage across scored stocks | **94%** |
| Cost | $0 |

---

## Quick start

```bash
pip install -r requirements.txt
export RANKFIELD_USER_AGENT="Your Name your@email.com"   # SEC policy requires a real contact
python scripts/run_all.py
cd site && npm install && npm run dev
```

A full run takes roughly 25–40 minutes, almost all of it fetching EDGAR company facts. The
companyfacts cache in `data/.cache/` makes every later run far faster and is gitignored.

To iterate on the front end without re-running anything, the payloads already in
`site/public/data/` are enough.

---

## Layout

```
scripts/                 Python batch jobs, run in this order
  fetch_universe.py        universe + sector + market cap        -> data/universe.json
  fetch_prices.py          adjusted closes + liquidity           -> data/price_snapshot.json
  fetch_fundamentals.py    SEC EDGAR XBRL, point-in-time         -> data/fundamentals.json
  compute_scores.py        winsorize -> percentile -> factors    -> data/scores_*.json, history/
  build_json.py            publish payloads to the site
  run_all.py               all of the above, in order
  verify_fundamentals.py   print raw values for a sample, to eyeball before scaling
  test_split_handling.py   acceptance test: splits must not fake a monthly move
  rankfield/
    providers/             the ONLY place external data is fetched
    facts.py               point-in-time view over one company's XBRL facts
    metrics.py             the formula appendix, implemented
    scoring.py             segmentation, percentiles, composite, weight sweep
data/
  universe.json            ticker, name, sector, market cap, CIK
  scores_full.json         ranking + all sub-scores + provenance  (the paid-tier shape)
  scores_public.json       ranked list only                       (the free-tier shape)
  history/                 scores_YYYY-MM.json, append-only, never overwritten
  history_index.json       ticker -> [{month, composite, rank, price, factors}]
  coverage_report.json     the funnel, and every unresolved metric with its reason
site/                      React + Vite + TypeScript front end
  src/data/repository.ts   the single data-access module - no component fetches a URL
.github/workflows/
  monthly-score.yml        cron 0 6 2 * *  - full scoring run; pushing its data triggers the deploy
  weekly-prices.yml        cron 0 7 * * 6  - re-adjusts the scoring-date prices for splits/dividends
                                             (it does not show newer prices - those arrive monthly)
  deploy-site.yml          on push         - tests, build, publish to GitHub Pages
  tests.yml                on push         - Python and TypeScript test suites
```

> The architecture sketch in the brief lists `scores_latest.json` as well. It would be a
> byte-for-byte duplicate of `scores_full.json`, committed monthly, so it is not emitted —
> `scores_full.json` *is* the latest.

---

## The decisions that matter

**Nothing is ranked across the whole market.** Every metric is percentile-ranked within the
stock's own sector, inside its own model-validity segment. Cross-sector ranking is the single
biggest source of wrong answers in this kind of tool.

**Missing is missing.** A metric that cannot be computed is `null`, is logged to
`coverage_report.json` with a reason, and its weight is renormalised away. It is never imputed
as zero, which would silently punish a company for a tagging gap in its filings.

**Point-in-time, via `filed`.** Scoring as of date D uses only facts with `filed <= D`. EDGAR
never overwrites — restatements arrive as later filings — so any past score is reproducible.
This is why the pipeline uses `companyfacts` rather than the cheaper `frames` endpoint:
`frames` carries `accn` but not `filed`, and returns only the latest, possibly restated value.

**History is append-only and is never re-scored.** Changing the weights bumps
`weights_version` and starts a new series; the old series stays exactly as it was. Re-scoring
the past with today's weights guarantees a flattering backtest and destroys the evidential
value of the whole exercise.

**Both endpoints of a price change come from today's adjusted series.** Never from the number
stored last month — after a split that number is on the old basis and a 10-for-1 reads as −90%.
`scripts/test_split_handling.py` proves this against real splits (Netflix's 10-for-1 reports
+13.02%, not −90%).

**Growth is ROIC-conditioned.** Scored positively only where ROIC clears the cost-of-capital
hurdle, and inverted where it does not. Expanding while destroying value is not rewarded.

**Momentum is deliberately excluded.** It is entirely price, so including it would contaminate
the score-versus-price validation — partly testing whether past price predicts future price.

**Banks are not ranked against industrials.** Operating companies, financials & REITs, and
pre-revenue biotech are three separate tables. The four factors assume a normal operating
company, and JPMorgan legitimately has no gross margin.

---

## Corrections to the record

History is append-only, so any rewrite of a stored month is logged here. There has
been one.

**2026-09 — the 2026-08 record was regenerated once.** Growth in profitability
(dGPOA) subtracted a fiscal-year ratio from a trailing-twelve-month one, so the
near endpoint used a balance sheet up to six months newer than the far endpoint.
Companies growing their asset base were penalised for where their fiscal year
fell rather than for their economics, and 1,108 of 1,354 rows were mis-ranked.
Microsoft, whose fiscal year already aligned with the scoring date, was the only
large name unaffected - which is what identified it as a calendar artifact.

The record was corrected in the same month it was written, before any track
record depended on it. The original is preserved in git history at commit
`fb17365~1`. This is the exception the rule tolerates: a defect in a metric,
caught immediately. It is **not** licence to re-score history when the weights
change - that remains forbidden, because it guarantees a flattering backtest.

---

## Configuration

`config/weights.json` — the official factor weights, versioned. Changing them **must** bump
`version`; historical records keep the weights that produced them.

`config/settings.json` — floors and thresholds: market-cap floor, liquidity floor, coverage
threshold, minimum sector cohort, winsorization percentiles, the ROIC hurdle, and the weight
sweep used for the stability indicator.

---

## Known limitations, stated rather than hidden

- **Large banks are unranked.** JPMorgan, Bank of America and Progressive resolve 2–3 of the
  7 metrics applicable to the financials segment and land in *Insufficient data*. The four
  factors genuinely do not describe a bank; ranking one on three metrics would produce a
  number that looks like a judgement without being one. Sector-specific factor models are the
  fix, and they are a later enhancement, not a v1 claim.
- **Successor registrants lose their history.** ExxonMobil's ticker now maps to a newly created
  holding-company CIK with a single filing on record, so it fails the eight-filings test and is
  excluded with that reason named. Following predecessor CIKs is not automated.
- **Utilities have no GPOA.** Most do not tag a cost-of-revenue line at all, so gross profits
  over assets is null for them and Quality rests on ROIC and earnings variability.
- **Earnings estimate revisions are out of reach.** The most commercially validated signal in
  this field needs analyst estimates, which no free source provides. The methodology page says
  so plainly rather than implying parity with Zacks or Seeking Alpha Quant.
- **Price data cannot be redistributed.** See `SOURCES.md`. Fine for personal research; swap
  the provider before charging anyone.

---

## Deferred to v2 (deliberately, not forgotten)

Per-stock price charts with time slicers and 3-stock comparison, and the full portfolio with
shares, cost basis and valuation. Both are purely additive — they introduce no new fields into
the score payload — so deferring them costs nothing later.

What is **not** deferred, because it cannot be reconstructed afterwards: score history from run
1, `weights_version` on every record, the watchlist as a timestamped event log, the coverage
report, and both payload tiers.

---

Information only, not investment advice. Rankfield is not a registered investment adviser.
