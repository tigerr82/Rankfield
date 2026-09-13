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

  const observations = useMemo(
    () => Math.max(1, ...heldRows.map((row) => (history[row.ticker] ?? []).length)),
    [heldRows, history],
  );

  if (!holdings.length) return null;

  return (
    <section className="section">
      {/* One strip instead of a heading, three cards and two paragraphs. Every
          figure stays visible; the explanations that used to sit under each one
          are now its tooltip, so they cost no height until someone asks. */}
      <div className="pfstrip">
        <h2>My Portfolio</h2>
        <Metric label="Holdings" value={String(summary.holdings)} />
        <Metric
          label="Avg score"
          value={summary.avgComposite?.toFixed(1) ?? "—"}
          sub={`vs ${summary.universeAvgComposite?.toFixed(1) ?? "—"} universe`}
          title="Average Rankfield Score of your holdings against the whole table - are you actually holding higher-scoring stocks?"
        />
        <Metric
          label="Avg 1-mo"
          value={percent(summary.avgChange)}
          title="Average price change of your current holdings. Descriptive only: a position added after the window opened did not earn this return, so it is not a measured result."
        />
        <Metric
          label="Spread vs universe"
          value={summary.measurable ? percent(summary.spread) : "—"}
          title={
            summary.measurable
              ? `Portfolio ${percent(summary.portfolioReturn)} vs universe ${percent(summary.universeReturn)}, ${windowStart} → ${windowEnd}. Equal-weighted on both sides; ${summary.measurable} position${summary.measurable === 1 ? "" : "s"} held across the whole window.`
              : `Measured only over positions held across the whole window (${windowStart} → ${windowEnd}). None were, so there is no return to measure yet.`
          }
        />
        <Metric
          label="Sector-adj."
          value={summary.measurable ? percent(summary.sectorAdjustedSpread) : "—"}
          title="Each holding against its own sector's average. This isolates stock selection; the raw spread also includes sector allocation."
        />
        <span
          className="pfnote"
          title={`${summary.note ? summary.note + " " : ""}${summary.holdings} holdings over ${observations} monthly observation${observations === 1 ? "" : "s"} is a very small sample dominated by noise - these figures describe what happened, they do not establish skill.`}
        >
          {summary.measurable ? `${observations} mo · small sample` : "not measurable yet"}
        </span>
        <button type="button" className="linkbtn" onClick={clearHoldings}>
          Remove all
        </button>
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

function Metric({ label, value, sub, title }: { label: string; value: string; sub?: string; title?: string }) {
  return (
    <span className="pfm" title={title}>
      <span className="k">{label}</span>
      <span className="v mono">{value}</span>
      {sub && <span className="s">{sub}</span>}
    </span>
  );
}
