import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";
import { ScoreCell } from "../components/cells";
import { cleanName } from "../components/columns";
import { DASH, marketCap, metricValue, money, monthLabel, percent } from "../lib/format";
import { stockOutcomes } from "../lib/analytics";
import { compositeOf, isDefaultWeights } from "../lib/scoring";
import { useApp } from "../state/AppState";

/** Stable, shareable URL per stock: /stock/{TICKER}, linkable from day one.
 *  Retrofitting routing after launch breaks every link anyone has shared. */
export function StockPage() {
  const { ticker = "" } = useParams();
  const { scores, history, loading } = usePayload();
  const { weights } = useApp();
  const scrollRef = useScrollRef();
  const upper = ticker.toUpperCase();

  const row = useMemo(() => {
    if (!scores) return undefined;
    return Object.values(scores.segments).flat().find((r) => r.ticker === upper);
  }, [scores, upper]);

  const points = history?.tickers[upper] ?? [];
  const outcomes = useMemo(
    () => (history ? stockOutcomes(history, upper) : []),
    [history, upper],
  );

  if (loading) {
    return (
      <Shell scrollRef={scrollRef}>
        <div className="prose">Loading {upper}…</div>
      </Shell>
    );
  }

  if (!row) {
    const unranked = scores?.insufficient.find((r) => r.ticker === upper);
    return (
      <Shell scrollRef={scrollRef}>
        <div className="prose">
          <h1>{upper}</h1>
          {unranked ? (
            <>
              <p className="lede">This stock is in the universe but is not ranked.</p>
              <div className="callout caution">
                {unranked.reason}. Missing: {unranked.missing.join(", ") || "—"}.
              </div>
              <p>
                It is <b>unranked, not low-ranked</b>. A composite built on a handful of resolved
                metrics would look like a judgement without being one.
              </p>
            </>
          ) : (
            <p className="lede">
              No scored record for {upper} in the current run. It may not meet the market-cap or
              liquidity floors, or it may have been filtered by structural hygiene — the{" "}
              <Link to="/coverage">coverage report</Link> names every exclusion and its reason.
            </p>
          )}
          <p>
            <Link to="/">← Back to the rankings</Link>
          </p>
        </div>
      </Shell>
    );
  }

  if (!scores) return null;
  const live = compositeOf(row.factors, weights);
  const byFactor = new Map<string, (typeof scores.metrics)>();
  for (const m of scores.metrics) {
    if (!byFactor.has(m.factor)) byFactor.set(m.factor, []);
    byFactor.get(m.factor)!.push(m);
  }

  return (
    <Shell scrollRef={scrollRef}>
      <div className="prose" style={{ maxWidth: "104ch" }}>
        <p style={{ marginBottom: 4 }}>
          <Link to="/">← Rankings</Link>
        </p>
        <h1>
          {row.ticker} <span style={{ color: "var(--ink-3)", fontSize: 20 }}>{cleanName(row.name)}</span>
        </h1>
        <p className="lede">
          {row.sector} · {row.exchange} · {marketCap(row.market_cap)} ·{" "}
          {scores.segments_meta.find((s) => s.key === row.segment)?.label}
        </p>

        <div className="grid2" style={{ marginBottom: 18 }}>
          <Stat
            label={isDefaultWeights(weights) ? "Rankfield Score" : "Rankfield Score (what-if weights)"}
            value={live?.toFixed(1) ?? DASH}
            sub={
              isDefaultWeights(weights)
                ? `rank ${row.rank} in its table · decile ${row.sector_decile ?? DASH} of its sector`
                : `official score ${row.composite?.toFixed(1) ?? DASH} at ${row.weights_version} weights — the session weighting is exploratory and is not stored`
            }
          />
          <Stat label={`Price at ${row.price_at_scoring_asof}`} value={money(row.price)} sub={row.prior_price_date ? `${percent(row.price_change_pct)} vs ${money(row.prior_price)} on ${row.prior_price_date}` : "no prior scoring date — first run for this stock"} />
          <Stat
            label="Fundamentals as of"
            value={row.fundamentals_asof ?? DASH}
            sub={row.form ? `${row.form} filed ${row.filed} · accession ${row.accn}` : "no filing provenance"}
          />
          <Stat
            label="Rank stability"
            value={row.stability ? `${row.stability.rank_min}–${row.stability.rank_max}` : DASH}
            sub={row.stability ? `across ${row.stability.weightings_tested} plausible weightings` : "not computed"}
          />
        </div>

        <h2>Sub-scores</h2>
        <table>
          <thead>
            <tr>
              <th className="al-l">Factor / metric</th>
              <th className="al-r">Raw value</th>
              <th className="al-r">Sector percentile</th>
              <th className="al-l">Definition</th>
            </tr>
          </thead>
          <tbody>
            {scores.factors.map((factor) => (
              <>
                <tr key={factor.key} style={{ cursor: "default", background: "var(--surface-2)" }}>
                  <td className="al-l" style={{ fontWeight: 700 }}>{factor.label}</td>
                  <td className="al-r" />
                  <td className="al-r"><ScoreCell value={row.factors[factor.key]} /></td>
                  <td className="al-l" style={{ color: "var(--ink-3)", fontSize: 11.5 }}>
                    {factor.price_dependent ? "contains price by construction" : "price-independent"}
                  </td>
                </tr>
                {(byFactor.get(factor.key) ?? []).map((metric) => {
                  const cell = row.metrics[metric.key];
                  return (
                    <tr key={metric.key} style={{ cursor: "default" }}>
                      <td className="al-l" style={{ paddingLeft: 22 }}>{metric.label}</td>
                      <td className="al-r mono">{metricValue(cell?.raw ?? null, metric)}</td>
                      <td className="al-r"><ScoreCell value={cell?.pct ?? null} /></td>
                      <td className="al-l" style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                        {row.missing_reasons[metric.key] ?? metric.formula}
                      </td>
                    </tr>
                  );
                })}
              </>
            ))}
          </tbody>
        </table>

        <h2>Score history</h2>
        {points.length > 1 ? (
          <table>
            <thead>
              <tr>
                <th className="al-l">Month</th>
                <th className="al-r">Score</th>
                <th className="al-r">Rank</th>
                <th className="al-r">Price</th>
                <th className="al-l">Weights</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.month} style={{ cursor: "default" }}>
                  <td className="al-l">{monthLabel(p.month)}{p.backtested && <span className="basis">BACKTEST</span>}</td>
                  <td className="al-r mono">{p.composite?.toFixed(1) ?? DASH}</td>
                  <td className="al-r mono">{p.rank ?? DASH}</td>
                  <td className="al-r mono">{money(p.price)}</td>
                  <td className="al-l mono" style={{ fontSize: 11 }}>v{p.weights_version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="callout">
            History begins accumulating from the first run — there is one stored month so far. Month
            2 gives the first change value, and a trend becomes readable around months 4–6. There is
            no external source to reconstruct past Rankfield scores from, which is why the record is
            written from run 1 rather than added later.
          </div>
        )}

        {outcomes.length > 0 && (
          <>
            <h2>Score against subsequent return</h2>
            <div className="callout caution">
              <b>Illustrative, not evidence.</b> One stock over one period is a single noisy
              observation and cannot validate or refute the method. The{" "}
              <Link to="/validation">validation view</Link> is where the question is actually tested,
              across deciles and against the universe average.
            </div>
            <ul>
              {outcomes.map((o) => (
                <li key={o.from}>
                  Scored {o.score.toFixed(1)} in {monthLabel(o.from)} → {percent(o.ret)} over the
                  following {monthLabel(o.to)}.
                </li>
              ))}
            </ul>
          </>
        )}

        {row.notes.length > 0 && (
          <>
            <h2>Notes on this record</h2>
            <ul>
              {row.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Shell>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="stat">
      <span className="k">{label}</span>
      <span className="v">{value}</span>
      <div className="sub">{sub}</div>
    </div>
  );
}
