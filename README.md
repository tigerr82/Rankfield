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
| Scored | **1,380** (1,185 operating · 178 financials & REITs · 17 pre-revenue) |
| Routed to *Insufficient data* | 469 |
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
  check_drift.py           monthly data-drift gate (opens an issue; blocks on a collapse)
  run_all.py               all of the above, in order
  verify_fundamentals.py   print raw values for a sample, to eyeball before scaling
  test_split_handling.py   acceptance test: splits must not fake a monthly move
  rankfield/
    providers/             the ONLY place external data is fetched
    facts.py               point-in-time view over one company's XBRL facts
    metrics.py             the formula appendix, implemented
    scoring.py             segmentation, percentiles, composite, weight sweep
    drift.py               month-over-month drift report and its issue text
data/
  universe.json            ticker, name, sector, market cap, CIK
  scores_full.json         ranking + all sub-scores + provenance  (the paid-tier shape)
  scores_public.json       ranked list only                       (the free-tier shape)
  history/                 scores_YYYY-MM.json, append-only, never overwritten
  history_index.json       ticker -> [{month, composite, rank, price, factors}]
  coverage_report.json     the funnel, every unresolved metric with its reason, every stale input ignored
  drift_report.json        what changed since last month's run: lost metrics, abandoned tags, candidates
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

History is append-only, so any rewrite of a stored month is logged here. There have
been eight, all to the first month, before any comparison depended on it.

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


**2026-09 — methodology 1.1, and the 2026-08 baseline recomputed under it.** The Growth
factor averaged revenue growth with dGPOA, but dGPOA measures efficiency, not growth: a
company holding its asset base flat while selling a little more scored as a fast grower.
Adobe, growing revenue 10.5% a year, ranked first in Technology and outscored Alphabet
(12.5%) and Microsoft (16.1%) on "Growth". Growth is now revenue growth alone, ROIC-
conditioned as before; dGPOA moved to Quality, where Quality-Minus-Junk places it, and is
no longer inverted by the ROIC hurdle. Weights are unchanged at 25/25/25/25; the version
moved to 1.1 because the factor composition changed.

Effect on the baseline: 1,163 of 1,368 rows re-ranked. In Technology, Adobe 1 -> 7,
Microsoft 46 -> 33, Alphabet 73 -> 66, Apple 61 -> 99 (1.8% revenue growth, previously
lifted by its efficiency gain). Fourteen more stocks became scorable, because dGPOA is no
longer dropped when ROIC is unknown. The August record was regenerated because it is the
baseline every later month is compared against; the 1.0 version is preserved in git.


**2026-09 — methodology 1.2, and the 2026-08 baseline recomputed under it.** Two defects
put G-III Apparel first of 1,191, with revenue shrinking and earnings about to halve:

- *The ROIC hurdle rewarded decline.* Below the hurdle the growth percentile was inverted
  (100 - p), which punished value-destroying expansion but also turned the fastest-shrinking
  companies into the best "growers". G-III, revenue falling 2.9% a year with ROIC at 8.8%
  against a 9% hurdle, scored 88.6 on Growth; 148 companies with shrinking revenue scored 70
  or more. Below the hurdle the score is now min(p, 100 - p): never above 50, faster growth
  still penalised, shrinkage no longer rewarded. Methodology 1.1 had made this worse, because
  with Growth reduced to a single metric nothing diluted the inversion.
- *Proxy statements overwrote audited figures.* Pay-versus-performance tables in DEF 14A
  filings carry XBRL-tagged net income, often at the wrong scale, and the most recently filed
  value wins. For 26 scored companies (Medtronic, FedEx, Arista, G-III) net income arrived
  ~1000x too small, return on assets flattened to zero, and earnings variability read as
  perfectly stable. Figures now come only from 10-K, 10-Q, 20-F and 40-F reports and their
  amendments.

Effect: 1,331 of 1,368 rows re-ranked. G-III 1 -> 159 (Growth 88.6 -> 11.9, earnings
variability 0.005% -> 5.3%). No company with shrinking revenue now scores 70+ on Growth
(was 148), and none shows implausibly perfect earnings stability (was 11). In Technology:
Adobe 7 -> 5, Microsoft 33 -> 26, Alphabet 66 -> 55. The 1.1 record is preserved in git.


**2026-09 — figures from abandoned XBRL tags, and the 2026-08 baseline recomputed.** EDGAR
keeps every tag a company has ever used. Looking a tag up by priority returned its last value
however old, so figures from years ago stood in for current ones: Microsoft's total debt was
$31.8B from a 2015 10-Q (it is $40.3B), Johnson & Johnson's operating income dated from 2015,
GE's from 2012, and Deere's gross profit subtracted 2018 cost of goods from 2026 revenue. 557
of 1,368 scored companies carried at least one such figure, and 82 had a headline
"fundamentals as of" date more than a year old.

- *Freshness rule.* An input older than 300 days before the company's latest balance sheet is
  treated as not reported; a trailing figure built from quarters must reach the latest quarter
  (120 days). The latest balance sheet is the latest date at least five balance-sheet tags
  share, so one abandoned tag cannot anchor it (Cinemark).
- *Fallbacks the stale figures had been hiding.* Rejecting stale figures alone would have
  removed 224 companies, Lilly and Johnson & Johnson among them. Companies with no
  operating-income line now use pre-tax income plus interest expense; more debt tags are read
  (convertible, senior and unsecured notes); a company whose last reported debt was exactly zero
  and that tags none since has zero debt; two cost-of-revenue and capital-expenditure spellings
  were added. Interest on bank deposits is deliberately not added back — it would give JPMorgan
  an "EBIT" that means nothing.
- *Not fixed, stated instead.* Where a company's current figure is not in SEC's standard data
  at all — Ford's debt, Vertex's, most of Cinemark's statements — the metric is missing and the
  company may land in *Insufficient data*. Before, those companies were ranked on figures up to a
  decade old.

Weights and factor definitions are unchanged, so the version stays 1.2. Effect: 1,260 of 1,268
rows present in both versions re-ranked (operating median move 22 places); 100 left the ranking
(Citigroup, American Express, Vertex, Ford) and 108 joined (Merck, Goldman Sachs, IBM, Pfizer,
Shopify, Progressive). Deckers stays first; Microsoft 177 -> 164, TJX 271 -> 160, Deere
832 -> 355, KLA 828 -> 473, Lilly 90 -> 182, Casey's 34 -> 393. No scored row now rests on
fundamentals older than twelve months. The previous record is preserved in git.


**2026-09 — methodology 1.3, and the 2026-08 baseline recomputed under it.** Two defects in
revenue, found because Micron scored 37 on Growth while its revenue more than doubled:

- *Growth lagged by up to a year.* It was the CAGR of three completed fiscal years. On the
  31 August scoring date Micron's latest 10-K covered the year to August 2025, and its base year
  was the previous memory-cycle peak, so it read 6.7% while trailing revenue had grown from $37B
  to $90B. For 79% of companies the last fiscal year ends more than six months before the latest
  balance sheet. Growth is now the annual rate of the trend line through three years of
  trailing-twelve-month revenue, one point per quarter. The fiscal-year CAGR is the fallback when
  there are fewer than nine points, when the revenue base is under $50M, or when the quarters
  disagree with the restated annual report by more than 5% — quarterly comparatives are not
  restated after a spin-off or disposal (GE, AppLovin, Philip Morris among 61 companies).
  Full-year figures tagged in a quarter's context (L3Harris, NiSource) are discarded.
- *Revenue was sometimes a subset.* With both total revenue and revenue from contracts with
  customers tagged, priority picked the subset: Green Plains $0.19B instead of $2.09B (its
  "growth" read +34% while revenue shrank ~17% a year), United Rentals $3.7B instead of $16.4B,
  ADM $25B instead of $82B. The tags nest, so the largest now wins. Trailing revenue changed for
  128 companies.

Weights are unchanged; the version moved to 1.3 because the Growth input changed. Effect: 1,317
of 1,376 rows re-ranked (operating median move 22 places); five companies became scorable.
Micron 256 -> 30 (third in Technology), Teradyne 482 -> 197, Alphabet 307 -> 261, Green Plains
30 -> 482, Microsoft 164 -> 185, GE 357 -> 373 (annual fallback); Deckers stays first. The 1.2
record is preserved in git.


**2026-09 — methodology 1.4: every metric current to the latest quarter, and the 2026-08
baseline recomputed under it.** Micron's change in gross profitability read −3.0 points while
its gross margin rose from 56% to 85% over three quarters, which prompted an audit of every
input behind every metric for figures older than the company's latest report:

- *Fiscal-year metrics lagged by up to a year.* For 80% of companies the last fiscal year ends
  more than six months before the latest balance sheet. The change in gross profitability is
  now the three-year change on the trend line through quarterly GPOA (twelve-month gross
  profit over total assets at the same quarter end); earnings variability uses five
  twelve-month windows ending at the latest quarter. Fiscal years remain the fallback, and
  the quarterly versions are rejected where the quarters disagree with the restated annual
  report or are implausible (a quarter's gross profit above three times its assets).
- *Debt came from the first path in priority order, not the most recent.* 70 companies read
  their debt from the last 10-K although a newer balance sheet reported it (Lilly,
  UnitedHealth, Verizon, Qualcomm). The most recent complete path now wins; a component tag
  (convertible or senior notes alone) cannot replace an older total it falls far below
  (TeraWulf), while a smaller newer *total* is a repayment and stands (CSW Industrials).
  Several companies had near-zero debt on stale figures: Ball, Sunrun, Matador, Teradata.
- *Revenue across a restatement.* Taking the largest nested revenue tag (1.3) could pick a
  pre-restatement figure from an older filing: Crane NXT's 2022 revenue read as
  pre-separation Crane. The largest tag is now taken within the latest filing only.
- *A fiscal-year dGPOA whose cost tag changed meaning* - Asbury's 2022 cost of sales is a $0.9B
  component, its 2025 the full $14.9B - is left missing rather than reported as −154 points.
- *Companies that stopped filing.* A company whose latest report ends more than 200 days before
  the scoring date is no longer scored on it (IDACORP, Hub Group).

What was checked and left alone: trailing figures are current to the latest quarter for
97-99% of companies; the exceptions are items a company reports only annually (interest
expense, some D&A), which are the latest figures that exist.

Weights are unchanged; the version moved to 1.4 because two metric definitions changed.
Effect: 1,302 of 1,379 rows present in both versions re-ranked (operating median move 12
places). Micron 30 -> 20, Qualcomm 365 -> 261, Crane NXT 843 -> 669; Ball 238 -> 728 and
Sunrun 459 -> 1,142 on their actual debt. Deckers stays first. The 1.3 record is preserved in git.


**2026-09 — methodology 1.5: steady improvement is not instability, and the 2026-08 baseline
recomputed under it.** Earnings variability was the standard deviation of five return-on-assets
points around their mean, so a company improving every year scored as erratic as a cyclical:
Palantir, whose ROA rose from −16% to 26%, sat in the 11th percentile. Where the five points
trend upward, only the swings around the trend line now count. Where they trend downward the
plain standard deviation stands - measured around a falling trend, Devon Energy's slide from
23% to 5% read as stable in simulation, which is why the adjustment is one-sided. Cycles stay
volatile either way (Micron, Western Digital).

Weights are unchanged; the version moved to 1.5 because the metric's definition changed.
Effect: small - operating median rank move 7 places, correlation with 1.4 at 0.998. Palantir
134 -> 100, Carpenter Technology 303 -> 164, AppLovin 58 -> 54; Micron 20 -> 21; Deckers stays
first. The 1.4 record is preserved in git.


**2026-09 — the 2026-08 baseline rebuilt from a fresh EDGAR download.** A clean-clone
reproduction from GitHub, fetching every company fresh as the monthly job does, matched the code
exactly but not the data: the local companyfacts copy used for the regenerations above lacked
the June 10-Qs of five companies, filed in late July and so inside the point-in-time window -
Corning, Capital One, American Tower, Expand Energy and Ares Capital. The baseline now uses the
fresh download (Corning 596 -> 466, Expand Energy 255 -> 82; 34 other rows moved more than three
places). Committed regenerations now always fetch fresh (`fetch_fundamentals.py --no-cache`).

---

## Configuration

`config/weights.json` — the official factor weights, versioned. Changing them **must** bump
`version`; historical records keep the weights that produced them.

`config/settings.json` — floors and thresholds: market-cap floor, liquidity floor, coverage
threshold, minimum sector cohort, winsorization percentiles, the ROIC hurdle, the maximum age of
an input (`max_input_age_days`), the drift thresholds, and the weight sweep used for the
stability indicator.

### Monthly data-drift check

Companies move figures between XBRL tags. Measured over 2022–2026, about 1.6% of inputs a year
switch tag and are absorbed by the fallback chains, and about 0.6% — roughly three inputs a month
across the scored universe — move to a tag no chain reads. The freshness rule turns those into
gaps, never into wrong numbers, but gaps accumulate if nobody looks.

`compute_scores.py` writes `data/drift_report.json`: companies that left the ranking, metrics
lost since last month (economic losses such as negative EBITDA are listed separately), tags
companies recently stopped using, and for each the tags the company reports today that no list
reads. In the monthly workflow `check_drift.py` then:

- **warn** — anything to review: opens a GitHub issue with the tables, and publishes.
- **block** — the scored universe fell by 5% or more (usually a taxonomy change): opens the
  issue and stops before committing, so nothing is published until the lists are fixed.

Fixing a warning is normally one line in a tag list in `scripts/rankfield/metrics.py`, plus a
test.

---

## Known limitations, stated rather than hidden

- **Large banks are unranked.** JPMorgan, Bank of America, Wells Fargo and Morgan Stanley
  resolve 2 of the 8 metrics applicable to the financials segment and land in *Insufficient
  data*. The four
  factors genuinely do not describe a bank; ranking one on three metrics would produce a
  number that looks like a judgement without being one. Sector-specific factor models are the
  fix, and they are a later enhancement, not a v1 claim.
- **Some current figures are not in SEC's standard data.** Ford reports its debt split between
  Ford and Ford Credit in a form the companyfacts API does not carry; Cinemark stopped tagging
  its consolidated statements in standard form. Those metrics are missing, and such companies
  can land in *Insufficient data*. Reading full filing documents would close the gap; it is not
  done.
- **Hedged producers' revenue includes derivative gains and losses.** Natural-gas producers
  such as CNX report hedging results inside revenue, so revenue swings with gas prices and
  hedge marks (CNX: $1.3B, $3.4B, $1.3B, $2.2B in 2022–2025). Any growth measure on that line —
  CAGR or trend — is dominated by the hedge book, not by the business.
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
