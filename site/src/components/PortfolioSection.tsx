import { useMemo, type RefObject } from "react";
import type { FactorSpec, HistoryPoint, MetricSpec, StockRow } from "../data/types";
import { summarisePortfolio } from "../lib/analytics";
import { percent } from "../lib/format";
import { rankRows, type Weights } from "../lib/scoring";
import { useApp } from "../state/AppState";
import { RankTable } from "./RankTable";

interface Props {
  universe: StockRow[];
  metrics: MetricSpec[];
  factors: FactorSpec[];
  history: Record<string, HistoryPoint[]>;
  scrollRef: RefObject<HTMLElement | null>;
  official: Weights;
  windowStart: string;
  windowEnd: string;
}

/**
 * My Portfolio — the starred rows, in exactly the same columns as the main
 * table, above it. The summary answers the question the user actually has:
 * am I beating the field, and is that selection or just sector exposure?
 */
export function PortfolioSection({ universe, metrics, factors, history, scrollRef, official, windowStart, windowEnd }: Props) {
  const { holdings, watchEvents, weights, clearHoldings } = useApp();

  const heldRows = useMemo(
    () => universe.filter((row) => holdings.includes(row.ticker)),
    [universe, holdings],
  );
  const ranked = useMemo(
    () => rankRows(heldRows, weights, official),
    [heldRows, weights, official],
  );
  const summary = useMemo(
    () => summarisePortfolio(heldRows, universe, watchEvents, windowStart, windowEnd),
    [heldRows, universe, watchEvents, windowStart, windowEnd],
  );

  if (!holdings.length) return null;

  return (
    <section className="section">
      <div className="sechead">
        <h2>My Portfolio</h2>
        <span className="meta">
          {summary.holdings} holding{summary.holdings === 1 ? "" : "s"} · avg score{" "}
          {summary.avgComposite?.toFixed(1) ?? "—"} · avg 1-month {percent(summary.avgChange)}
        </span>
        <button type="button" className="linkbtn" onClick={clearHoldings}>
          Remove all
        </button>
      </div>

      <div className="card" style={{ margin: "0 0 10px" }}>
        <div className="grid2">
          <Stat
            label={`Spread vs universe (${windowStart} → ${windowEnd})`}
            value={summary.measurable ? percent(summary.spread) : "—"}
            sub={
              summary.measurable
                ? `portfolio ${percent(summary.portfolioReturn)} vs universe ${percent(summary.universeReturn)} · equal-weighted both sides · ${summary.measurable} position${summary.measurable === 1 ? "" : "s"} measured`
                : "no position held across this window yet"
            }
          />
          <Stat
            label="Sector-adjusted spread"
            value={summary.measurable ? percent(summary.sectorAdjustedSpread) : "—"}
            sub="each holding against its own sector's average — this is stock selection; the figure on the left also contains sector allocation"
          />
          <Stat
            label="Average score vs universe"
            value={summary.avgComposite != null ? summary.avgComposite.toFixed(1) : "—"}
            sub={`universe average ${summary.universeAvgComposite?.toFixed(1) ?? "—"} — are you actually holding higher-scoring stocks?`}
          />
        </div>
        {summary.note && (
          <p className="note" style={{ margin: "11px 0 0" }}>
            {summary.note}
          </p>
        )}
        <p className="note" style={{ margin: "6px 0 0" }}>
          {summary.holdings} holdings over 1 monthly observation is a very small sample dominated by
          noise. These figures describe what happened; they do not establish skill.
        </p>
      </div>

      <RankTable
        rows={ranked}
        metrics={metrics}
        factors={factors}
        history={history}
        scrollRef={scrollRef}
        tag="pf"
        className="pfwrap"
      />

      {summary.measurable > 0 && (
        <div className="card" style={{ margin: "10px 0 0" }}>
          <div className="sechead">
            <h2>Per-holding contribution</h2>
          </div>
          <table>
            <thead>
              <tr>
                <th className="al-l" style={{ position: "static" }}>Ticker</th>
                <th className="al-r" style={{ position: "static" }}>1-Mo %</th>
                <th className="al-r" style={{ position: "static" }}>Sector avg</th>
                <th className="al-r" style={{ position: "static" }}>vs sector</th>
                <th className="al-l" style={{ position: "static" }}>Counted</th>
              </tr>
            </thead>
            <tbody>
              {summary.lines.map((line) => (
                <tr key={line.ticker} style={{ cursor: "default" }}>
                  <td className="al-l tk">{line.ticker}</td>
                  <td className="al-r mono">{percent(line.changePct)}</td>
                  <td className="al-r mono">{percent(line.sectorAvg)}</td>
                  <td className="al-r mono">{percent(line.sectorAdjusted)}</td>
                  <td className="al-l" style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                    {line.heldAtWindowStart ? "yes" : `added after ${windowStart}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
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
