import { Link } from "react-router-dom";
import type { FactorSpec, HistoryPoint, MetricSpec } from "../data/types";
import type { RankedRow } from "../lib/scoring";
import { DASH, metricValue, money } from "../lib/format";
import { ScoreCell } from "./cells";
import { cleanName } from "./columns";

/**
 * Inline expansion, never a modal: clicking a row opens it in place to show
 * every metric behind every factor, each with its raw value alongside its
 * sector percentile. This is the product's differentiator made literal - the
 * composite is traceable to its factors, and each factor to its inputs.
 */
export function RowExpansion({
  row,
  metrics,
  factors,
  history,
}: {
  row: RankedRow;
  metrics: MetricSpec[];
  factors: FactorSpec[];
  history: HistoryPoint[];
}) {
  const byFactor = new Map<string, MetricSpec[]>();
  for (const spec of metrics) {
    if (!byFactor.has(spec.factor)) byFactor.set(spec.factor, []);
    byFactor.get(spec.factor)!.push(spec);
  }

  return (
    <div className="expbox">
      <div className="exphead">
        <h3>
          <Link to={`/stock/${row.ticker}`} onClick={(e) => e.stopPropagation()}>
            {row.ticker}
          </Link>{" "}
          · {cleanName(row.name)} — sub-score breakdown
        </h3>
        <span className="meta">
          {row.sector ?? DASH} · scored {row.scoring_date} ·{" "}
          {row.prior_price_date
            ? `vs ${money(row.prior_price)} on ${row.prior_price_date}`
            : "no prior scoring date"}{" "}
          · fundamentals as of {row.fundamentals_asof ?? DASH}{" "}
          {row.form ? `(${row.form} filed ${row.filed})` : ""}
        </span>
      </div>

      <div className="facgrid">
        {factors.map((factor) => {
          const specs = (byFactor.get(factor.key) ?? []).slice().sort((a, b) => {
            const pa = row.metrics[a.key]?.pct ?? -1;
            const pb = row.metrics[b.key]?.pct ?? -1;
            return pb - pa;
          });
          return (
            <div className="faccard" key={factor.key}>
              <div className="fh">
                <span className="nm">{factor.label}</span>
                <ScoreCell value={row.factors[factor.key]} />
              </div>
              {specs.map((spec) => {
                const cell = row.metrics[spec.key];
                const basis = cell?.basis ?? "";
                return (
                  <div className="mrow" key={spec.key}>
                    <span className="ml" title={spec.formula}>
                      {spec.label}
                      {basis.includes("universe") && (
                        <span className="basis" title="Sector cohort too small — ranked against the whole segment">
                          SEG
                        </span>
                      )}
                      {basis.includes("below-hurdle") && (
                        <span className="basis inv" title="ROIC is at or below the cost-of-capital hurdle: growth cannot score above 50, and faster growth scores lower - value-destroying expansion is never rewarded">
                          HURDLE
                        </span>
                      )}
                    </span>
                    <span className="mv">
                      <span className="raw">{metricValue(cell?.raw ?? null, spec)}</span>
                      <ScoreCell value={cell?.pct ?? null} />
                    </span>
                  </div>
                );
              })}
              {!specs.length && <div className="mrow"><span className="ml">Not applicable to this segment</span></div>}
            </div>
          );
        })}
      </div>

      {row.stability && (
        <div className="miss" style={{ borderTopStyle: "solid" }}>
          <b>Rank stability.</b> Ranks between {row.stability.rank_min} and {row.stability.rank_max}{" "}
          across {row.stability.weightings_tested} plausible weightings (each factor swept 10–40%).{" "}
          {row.stability.rank_max - row.stability.rank_min <= 25
            ? "A narrow range: this position does not depend on one specific weighting."
            : "A wide range: this position depends heavily on how the factors are weighted."}
        </div>
      )}

      {row.missing.length > 0 && (
        <div className="miss">
          <b>Not reported for this company:</b>{" "}
          {row.missing
            .map((key) => {
              const spec = metrics.find((m) => m.key === key);
              return `${spec?.label ?? key} (${row.missing_reasons[key] ?? "unavailable"})`;
            })
            .join("; ")}
          . Excluded from scoring and the remaining weights renormalised — never scored as zero.
        </div>
      )}

      {history.length > 1 && (
        <div className="miss" style={{ borderTopStyle: "solid" }}>
          <b>Score history.</b>{" "}
          {history
            .slice(-12)
            .map((p) => `${p.month}: ${p.composite?.toFixed(1) ?? DASH}`)
            .join(" · ")}
        </div>
      )}
      {history.length <= 1 && (
        <div className="miss" style={{ borderTopStyle: "solid", color: "var(--ink-3)" }}>
          Score history begins accumulating from the first run. Month 2 gives the first change
          value; the trend column becomes meaningful around months 4–6.
        </div>
      )}
    </div>
  );
}
