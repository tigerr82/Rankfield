import { usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";

/**
 * The methodology page is a credibility asset, not documentation. Every
 * competitor deliberately hides this. It states the formulas verbatim, names
 * the simplifications, and says plainly what Rankfield cannot do.
 */
export function MethodologyPage() {
  const { scores } = usePayload();
  const meta = scores?.meta;
  const hurdle = meta ? (meta.settings.scoring.roic_hurdle * 100).toFixed(0) : "9";
  const lo = meta?.settings.scoring.winsorize_lo_pct ?? 5;
  const hi = meta?.settings.scoring.winsorize_hi_pct ?? 95;
  const scrollRef = useScrollRef();

  return (
    <Shell scrollRef={scrollRef}>
      <div className="prose">
        <h1>Methodology</h1>
        <p className="lede">
          Every number on this site can be traced from the Rankfield Score down to the individual
          filing it came from. This page is the whole method — the factors, the formulas, the
          simplifications and the limits.
        </p>

        <h2>Sector-relative percentile scoring</h2>
        <p>
          Raw metrics are never ranked across the whole market. A bank&apos;s leverage and a software
          company&apos;s leverage are not comparable, and cross-sector ranking is the single biggest
          source of wrong answers in this kind of tool. For every metric, a stock is given its{" "}
          <b>percentile rank within its own sector</b>, and those percentiles are combined into
          factor scores. Where a sector cohort is too small to rank against, the stock is ranked
          against its whole segment and the cell is marked <span className="basis">SEG</span>.
        </p>
        <p>
          Before ranking, every metric is <b>winsorized at the {lo}th and {hi}th percentile</b>{" "}
          within its sector, so a single extreme ratio or a negative-equity company cannot distort
          the distribution. That follows MSCI&apos;s factor-index practice and is deliberately more
          aggressive than the 1/99 often used.
        </p>
        <p>
          A stock with no value for a metric is scored on its remaining metrics and the weights are
          renormalised. <b>A missing metric is never imputed as zero</b> — that would silently punish
          the company for a tagging gap in its filings. Every null is logged to the{" "}
          <a href="#/coverage">coverage report</a> with its reason.
        </p>

        <h2>Four factors, equally weighted</h2>
        <p>
          Each factor is 0–100 from sector-relative percentiles, and the Rankfield Score is their
          weighted blend — {meta ? Object.values(meta.weights).join("/") : "25/25/25/25"} under
          weights v{meta?.weights_version ?? "1.0"}. Each factor deliberately holds only three or
          four metrics: MSCI&apos;s Quality Index, with hundreds of billions benchmarked to it, uses
          exactly three. More metrics means more missing data, more mis-tagged XBRL and more noise.
        </p>

        {scores && (
          <table>
            <thead>
              <tr>
                <th className="al-l">Factor</th>
                <th className="al-l">Metric</th>
                <th className="al-l">Definition</th>
              </tr>
            </thead>
            <tbody>
              {scores.factors.map((factor) =>
                scores.metrics
                  .filter((m) => m.factor === factor.key)
                  .map((metric, i) => (
                    <tr key={metric.key} style={{ cursor: "default" }}>
                      {i === 0 && (
                        <td
                          className="al-l"
                          rowSpan={scores.metrics.filter((m) => m.factor === factor.key).length}
                          style={{ verticalAlign: "top", fontWeight: 600, color: "var(--ink)" }}
                        >
                          {factor.label}
                          {factor.price_dependent && (
                            <div style={{ fontWeight: 400, fontSize: 11, color: "var(--ink-3)", marginTop: 3 }}>
                              contains price
                            </div>
                          )}
                        </td>
                      )}
                      <td className="al-l">{metric.label}</td>
                      <td className="al-l">{metric.formula}</td>
                    </tr>
                  )),
              )}
            </tbody>
          </table>
        )}

        <h3>Why these metrics, and what was deliberately left out</h3>
        <ul>
          <li>
            <b>EBIT/EV is the primary value metric</b>, replacing forward P/E and PEG. Gray &amp;
            Carlisle ranked EBIT/EV first and EBITDA/EV second; book-to-market ranked last.
            Separately, forward P/E and PEG require analyst estimates, which SEC EDGAR does not
            provide — they are not obtainable on a free data stack at all.
          </li>
          <li>
            <b>Gross profits over assets</b> (Novy-Marx) is roughly as predictive as book-to-market
            and works on growth stocks where value screens fail.
          </li>
          <li>
            <b>Earnings variability</b> is used by both MSCI and Stockopedia as a quality input.
          </li>
          <li>
            <b>Current ratio was removed</b> — weak evidence as a return predictor. The Altman
            Z-score replaces it.
          </li>
          <li>
            <b>ROIC is the primary quality metric.</b> Practitioner frameworks treat return on
            invested capital against the cost of capital as the central organising variable.
          </li>
          <li>
            <b>Momentum is excluded, and that is a decision, not an oversight.</b> Momentum is
            entirely price, so including it would contaminate the score-versus-price validation —
            partly testing whether past price predicts future price. It also cannot be explained
            from a company&apos;s filings, which is what this product is for.
          </li>
        </ul>

        <h2>Growth is ROIC-conditioned</h2>
        <p>
          Raw growth does not predict returns. But growth is not useless — it is{" "}
          <i>conditional</i>: growth increases multiples when returns are above the cost of capital
          and decreases them when returns are below. So growth is scored positively only where ROIC
          exceeds an assumed cost of capital, and <b>scored negatively where it does not</b> — a
          company expanding while destroying value is not rewarded for it.
        </p>
        <pre>{`if ROIC >  ${hurdle}% (hurdle):   growth percentile used as-is
if ROIC <= ${hurdle}% (hurdle):   min(p, 100 - p)   (never above 50; faster growth scores lower)`}</pre>
        <p>
          A flat hurdle stands in for a company-specific cost of capital. That is a simplification,
          stated here rather than hidden. Where ROIC itself could not be computed, the growth metrics
          are dropped rather than guessed at: not knowing whether growth creates or destroys value is
          not a licence to reward it, and inverting on an unknown would punish arbitrarily.
        </p>

        <h2>Point-in-time discipline</h2>
        <p>
          <b>Only financial reports supply figures</b> — annual and quarterly reports and their
          amendments. Proxy statements are ignored: their pay-versus-performance tables repeat
          several years of net income in XBRL, frequently at the wrong scale, and because the most
          recently filed value wins they were overwriting audited figures with numbers a thousand
          times too small.
        </p>
        <p>
          EDGAR is a genuine point-in-time source, because every fact carries the date it was{" "}
          <code>filed</code>, the accession number of the filing, and the form type. Restatements
          arrive as later filings with later filed dates; EDGAR never overwrites. This is
          structurally better than several paid vendors, which historically overwrote restated
          figures.
        </p>
        <p>
          <b>When scoring as of date D, only facts with <code>filed &lt;= D</code> are used.</b> This
          also removes the reporting-lag trap: a quarter ending 31 March and filed on 10 May becomes
          visible on 10 May, never on 31 March. Fundamentals are never keyed off period-end dates.
          Each row records the fiscal period its metrics came from, so you can see whether a score
          rests on fresh or three-month-old filings.
        </p>
        <p>
          With roughly 2,400 companies on staggered fiscal year-ends, no run date makes every company
          current at once — some are scored on Q2 filings while others already have Q3. That is
          inherent to a monthly cadence, not a defect, which is why the filing date is shown per
          stock rather than implied to be uniform.
        </p>

        <h2>Prices and month-over-month change</h2>
        <p>
          All prices are <b>split- and dividend-adjusted closes</b>. The scoring date is the last
          trading day of the prior month, and the change column compares it to the prior scoring
          date. The price shown is therefore that day&apos;s close, not today&apos;s price: it moves
          forward once a month, at the next scoring run, and the table labels its date.
        </p>
        <div className="callout caution">
          <b>Both endpoints are read from today&apos;s adjusted series</b>, never from the price
          stored last month. If a stock splits between two runs, last month&apos;s stored price sits
          on the old basis, and comparing against it would read a 10-for-1 split as −90%. The
          originally stored price is kept for audit and never used in the calculation. Any monthly
          move beyond ±50% is logged for review, because a corporate action is the far more likely
          explanation than a real move.
        </div>

        <h2>Who gets scored</h2>
        <p>
          The full qualifying universe is scored — the default <i>view</i> is narrowed, not the
          scored set. Mega-caps are the most analysed and most efficiently priced segment of the
          market, so raising the size floor would delete exactly where a fundamental screen might
          still find something. Size is the wrong axis; liquidity is the right one.
        </p>
        <ol>
          <li>
            <b>Model validity.</b> The four factors assume a normal operating company. Banks,
            insurers, REITs and BDCs break them structurally — JPMorgan legitimately has no gross
            margin and therefore no meaningful Financial Health input — and pre-revenue biotech
            breaks growth and valuation the same way. These are ranked in{" "}
            <b>separate tables, never against each other</b>. Sector-specific factor models are a
            later enhancement, not a v1 claim.
          </li>
          <li>
            <b>Data coverage.</b> A stock resolving fewer than 70% of the metrics applicable to its
            segment is routed to <i>Insufficient data</i> — unranked, not low-ranked.
          </li>
          <li>
            <b>Structural hygiene.</b> Dual-class duplicates collapsed to one line per company
            (keyed on SEC filer, keeping the more liquid class); foreign private issuers filing 20-F
            removed; SPACs, shells, trusts and funds removed; at least eight periodic filings
            required, or growth metrics are unreliable.
          </li>
          <li>
            <b>Liquidity floor</b> on average daily dollar volume, the correct substitute for a size
            floor.
          </li>
        </ol>
        <p>
          The full funnel, with a count at every stage and a named reason for every exclusion, is in
          the <a href="#/coverage">coverage report</a>.
        </p>

        <h2>What Rankfield cannot do</h2>
        <div className="callout caution">
          <b>Earnings estimate revisions are the most commercially validated signal in this field.</b>{" "}
          Zacks is built entirely on them and claims +23.8% a year for its top rank since 1988;
          Seeking Alpha&apos;s Quant and Stockopedia&apos;s Momentum both use them. They require
          analyst estimates, which are not available on a free data stack. Rankfield therefore cannot
          replicate that edge, and does not claim parity with those products.
        </div>

        <h2>Exact formulas</h2>
        <p>
          Every metric below has more than one legitimate industry convention — Mauboussin shows ROIC
          for a single company ranging from 34% to 94% purely on methodology choices. One definition
          is picked, applied everywhere, and published here.
        </p>

        <h3>Quality</h3>
        <pre>{`ROIC (simplified, deliberately)
  NOPAT            = EBIT x (1 - effective tax rate)
  effective tax    = IncomeTaxExpenseBenefit / IncomeLossBeforeIncomeTaxes  (clamped 0-35%)
  Invested Capital = Total Debt + Total Shareholders' Equity - Cash & equivalents
  ROIC             = NOPAT / average Invested Capital (open + close / 2)

GPOA  = (Revenue - COGS) / Total Assets

Earnings variability
  ROA_t   = 12-month Net Income_t / Total Assets_t, for 5 years ending at the
            latest quarter and each anniversary before it
            (fallback: the last 5 fiscal years)
  EarnVar = if the ROA_t trend rises: standard deviation around the trend line
            otherwise:               standard deviation of ROA_t
            (lower is better, so inverted when scoring)

Change in gross profitability
  dGPOA   = 3-year change on the trend line through quarterly GPOA
            (12-month gross profit / total assets at the same quarter end)
            fallback: GPOA_latest FY - GPOA_(3 fiscal years earlier)`}</pre>
        <p>
          <b>Steady improvement is not instability, since methodology 1.5.</b> Measured around its
          mean, return on assets that climbs every year - Palantir from −16% to 26% - scored as
          erratic as a memory-chip cycle. Where the five points trend upward, only the swings around
          the trend line count. Where they trend downward the plain spread stands, because a steady
          slide in profitability is a weakening business, not a stable one. Micron, which fell into
          losses and then surged, stays near the bottom either way.
        </p>
        <p>
          <b>Every metric is current to the latest quarter, since methodology 1.4.</b> Fiscal years
          alone ended more than six months before the latest balance sheet for 80% of companies.
          On them Micron&apos;s change in gross profitability read −3.0 points (the previous memory-cycle
          peak to fiscal 2025) while its gross margin rose from 56% to 85% over three quarters. Both
          fiscal-year metrics now use trailing twelve-month windows ending at the latest quarter,
          with each window&apos;s figure divided by the balance sheet at its own date. Debt comes from
          the most recent balance sheet that reports it, and a company whose latest report is more
          than 200 days old is not scored.
        </p>
        <p>
          Mauboussin&apos;s full ROIC treatment — capitalised intangibles, operating-lease interest,
          excess-cash estimates — needs company-level judgment and cannot be automated reliably
          across 2,400 names. The simplified form is used, and consistency across companies matters
          more here than precision on any one of them. Where the effective tax rate cannot be
          computed (a loss-making period, or untagged), the US statutory 21% is used.
        </p>
        <p>
          Earnings variability uses the standard deviation of <b>return on assets</b> rather than
          MSCI&apos;s standard deviation of year-on-year EPS growth. EPS growth is undefined when EPS
          crosses zero, which happens often in a universe this size; ROA volatility measures the same
          thing and is always defined. A deliberate, documented deviation.
        </p>

        <h3>Value</h3>
        <pre>{`EV         = Market Cap + Total Debt - Cash & equivalents
EBIT/EV    = EBIT / EV
EBITDA/EV  = (EBIT + Depreciation & Amortisation) / EV
FCF/EV     = (Operating Cash Flow - Capital Expenditure) / EV`}</pre>
        <p>
          Minority interest and preferred stock are excluded from enterprise value, for consistency
          and availability. Market cap comes from the universe file, not from EDGAR. EBIT is rarely
          tagged directly, so operating income is used and, where absent, derived as revenue less
          cost of revenue less operating expenses — operating income approximates EBIT because it
          excludes non-operating items. Companies that present no operating-income line at all
          (Johnson &amp; Johnson, Lilly, Merck) use pre-tax income plus interest expense, the textbook
          EBIT.
        </p>
        <p>
          <b>Only current figures are used.</b> EDGAR keeps every tag a company has ever reported,
          including ones it abandoned years ago. Any input older than 300 days before the company's
          latest balance sheet is treated as not reported, and the next source in the chain is
          tried. Without this rule Microsoft's debt was read from a 2015 filing and Deere's gross
          profit subtracted 2018 costs from 2026 revenue. Where no debt tag is current and the last
          one reported was exactly zero, debt is zero; any other gap stays a gap.
        </p>

        <h3>Growth</h3>
        <pre>{`RevGrowth = annual growth rate of the trend line through
            3 years of trailing-12-month revenue, one point per quarter
            (fallback: 3-fiscal-year CAGR)

then, after the percentile step:
  if ROIC >  hurdle:  percentile used as-is
  if ROIC <= hurdle:  min(p, 100 - p)`}</pre>
        <p>
          <b>Growth is current to the latest quarter, since methodology 1.3.</b> Completed fiscal
          years alone lag by up to a year: on the 31 August 2026 scoring date Micron&apos;s latest
          annual report covered the year to August 2025, so a three-year CAGR measured from the
          previous memory-cycle peak read 6.7% while trailing revenue had grown from $37B to $90B.
          A trend line through every quarter is also less sensitive than a CAGR to whether its first
          year was a peak or a trough. The fiscal-year CAGR remains the fallback where the quarterly
          history is too short (under nine points), too small (a revenue base under $50M), or
          disagrees with the restated annual report — quarterly comparatives are not restated after
          a spin-off, so GE&apos;s quarters before GE Vernova describe a different company.
        </p>
        <p>
          <b>Revenue is the total, since methodology 1.3.</b> Companies often tag both total revenue
          and the part of it that comes from contracts with customers. Taking the first tag by
          priority read the subset: $0.19B instead of $2.09B for Green Plains, $3.7B instead of
          $16.4B for United Rentals, whose rental income is lease revenue. The largest of the nested
          revenue tags is now used.
        </p>
        <p>
          <b>Below the hurdle, growth is capped rather than inverted, since methodology 1.2.</b> A
          straight inversion (100 − p) punished value-destroying expansion as intended, but it also
          turned the fastest-shrinking companies into the best &ldquo;growers&rdquo;: a company whose
          revenue fell 2.9% a year scored 88.6 on Growth and ranked first overall. With min(p, 100 − p)
          a company below the hurdle can never score above 50 on Growth, whichever way its revenue
          moves.
        </p>
        <p>
          <b>Growth is revenue growth alone, since methodology 1.1.</b> It was originally the
          average of revenue growth and the change in gross profitability (dGPOA). But dGPOA
          measures efficiency, not growth: a company that holds its asset base flat while selling a
          little more scores as a fast grower. In practice a 10.5% revenue grower outscored 12.5%
          and 16.1% growers on &ldquo;Growth&rdquo;. dGPOA now sits in Quality, where
          Quality-Minus-Junk places it, and is not ROIC-conditioned.
        </p>

        <h3>Financial Health</h3>
        <pre>{`Debt/Equity     = Total Debt / Total Shareholders' Equity
Net Debt/EBITDA = (Total Debt - Cash) / EBITDA

Altman Z'' (the NON-MANUFACTURING variant, not the 1968 original)
  Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
  X1 = (Current Assets - Current Liabilities) / Total Assets
  X2 = Retained Earnings / Total Assets
  X3 = EBIT / Total Assets
  X4 = Book Value of Equity / Total Liabilities
  Safe > 2.6 · Grey 1.1-2.6 · Distress < 1.1`}</pre>
        <p>
          The 1968 original was fitted on manufacturers only, using the market value of equity and a
          sales-to-assets term. This universe is mixed-sector, so Z&apos;&apos; is the correct
          choice. Neither variant is applied to financials — they are in a separate table.
        </p>

        <h3>Edge cases, handled explicitly</h3>
        <table>
          <thead>
            <tr>
              <th className="al-l">Condition</th>
              <th className="al-l">Behaviour</th>
            </tr>
          </thead>
          <tbody>
            <tr style={{ cursor: "default" }}><td className="al-l">Negative shareholders&apos; equity</td><td className="al-l">Debt/Equity is null, not a large negative. Weights renormalised.</td></tr>
            <tr style={{ cursor: "default" }}><td className="al-l">Negative or zero EBITDA</td><td className="al-l">Net Debt/EBITDA is null. A negative multiple must never rank as cheap.</td></tr>
            <tr style={{ cursor: "default" }}><td className="al-l">Negative enterprise value</td><td className="al-l">All value metrics null.</td></tr>
            <tr style={{ cursor: "default" }}><td className="al-l">Negative EBIT or FCF</td><td className="al-l">The true negative is kept — genuinely poor, ranked accordingly.</td></tr>
            <tr style={{ cursor: "default" }}><td className="al-l">Zero or missing denominator</td><td className="al-l">Null, never zero.</td></tr>
            <tr style={{ cursor: "default" }}><td className="al-l">Fewer than 5 fiscal years</td><td className="al-l">Earnings variability null.</td></tr>
            <tr style={{ cursor: "default" }}><td className="al-l">Fiscal-year changes</td><td className="al-l">Periods aligned on end dates, never on fiscal labels.</td></tr>
          </tbody>
        </table>
        <p>
          <b>Null means excluded and the remaining weights renormalised — never imputed as zero.</b>
        </p>

        <h2>Sources</h2>
        <ul>
          <li>
            <b>Fundamentals:</b> SEC EDGAR XBRL company facts. US government work,{" "}
            <b>public domain</b> — no restriction on commercial use or redistribution.
          </li>
          <li>
            <b>Universe, sector and market cap:</b> the Nasdaq stock screener.
          </li>
          <li>
            <b>Prices:</b> {meta?.sources?.prices?.name ?? "the configured provider"} —{" "}
            {meta?.sources?.prices?.licence ?? "personal use"}. Fine for personal research; it does
            not grant redistribution rights, and must be swapped for a commercially licensed feed
            before this becomes a paid product.
          </li>
        </ul>
        <p style={{ color: "var(--ink-3)" }}>
          Information only, not investment advice. Rankfield is not a registered investment adviser.
        </p>
      </div>
    </Shell>
  );
}
