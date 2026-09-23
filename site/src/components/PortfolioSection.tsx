import { useMemo, type RefObject } from "react";
import type { FactorSpec, HistoryPoint, MetricSpec, SegmentKey, StockRow } from "../data/types";
import { summarisePortfolio } from "../lib/analytics";
import { percent } from "../lib/format";
import { rankRows, type RankedRow, type Weights } from "../lib/scoring";
import { useApp } from "../state/AppState";
import { RankTable } from "./RankTable";
import { SharePortfolioButton } from "./SharedPortfolio";

interface Props {
  /** Every scored segment. The portfolio is the user's, not the selected
   *  segment's, so it reads all of them and ignores the segment tab and filters. */
  segments: Record<SegmentKey, StockRow[]>;
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
 * table, above it, whichever segment is selected. The summary answers the
 * question the user actually has: am I beating the field, and is that
 * selection or just sector exposure?
 */
export function PortfolioSection({ segments, metrics, factors, history, scrollRef, official, windowStart, windowEnd }: Props) {
  const { holdings, watchEvents, weights, clearHoldings } = useApp();

  // Each holding keeps its rank within its own segment under the current
  // weights: scores are percentiles within a segment, so that is the only rank
  // that means anything. The portfolio then lists them by score.
  const heldRows: RankedRow[] = useMemo(() => {
    const held = new Set(holdings);
    const out: RankedRow[] = [];
    for (const rows of Object.values(segments)) {
      if (!rows.some((row) => held.has(row.ticker))) continue;
      for (const row of rankRows(rows, weights, official)) if (held.has(row.ticker)) out.push(row);
    }
    return out.sort((a, b) => (b.liveComposite ?? -1) - (a.liveComposite ?? -1));
  }, [segments, holdings, weights, official]);

  // The benchmark is every scored stock, not the segment on screen: a figure
  // about your portfolio must not change when you switch tabs.
  const universe = useMemo(() => Object.values(segments).flat(), [segments]);
  const summary = useMemo(
    () => summarisePortfolio(heldRows, universe, watchEvents, windowStart, windowEnd),
    [heldRows, universe, watchEvents, windowStart, windowEnd],
  );

  // Holdings with no score this month - routed to Insufficient data, or no
  // longer in the universe - are named rather than silently dropped.
  const unscored = useMemo(() => {
    const scored = new Set(heldRows.map((row) => row.ticker));
    return holdings.filter((ticker) => !scored.has(ticker));
  }, [holdings, heldRows]);

  const mixedSegments = useMemo(() => new Set(heldRows.map((row) => row.segment)).size > 1, [heldRows]);

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
        <Metric label="Holdings" value={String(holdings.length)} />
        <Metric
          label="Avg score"
          value={summary.avgComposite?.toFixed(1) ?? "—"}
          sub={`vs ${summary.universeAvgComposite?.toFixed(1) ?? "—"} universe`}
          title={`Average Rankfield Score of your holdings against all ${universe.length.toLocaleString()} scored stocks - are you actually holding higher-scoring stocks?`}
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
              ? `Portfolio ${percent(summary.portfolioReturn)} vs all scored stocks ${percent(summary.universeReturn)}, ${windowStart} → ${windowEnd}. Equal-weighted on both sides; ${summary.measurable} position${summary.measurable === 1 ? "" : "s"} held across the whole window.`
              : `Measured only over positions held across the whole window (${windowStart} → ${windowEnd}). None were, so there is no return to measure yet.`
          }
        />
        <Metric
          label="Sector-adj."
          value={summary.measurable ? percent(summary.sectorAdjustedSpread) : "—"}
          title="Each holding against its own sector's average. This isolates stock selection; the raw spread also includes sector allocation."
        />
        {unscored.length > 0 && (
          <span
            className="pfnote"
            title="No Rankfield Score this month: routed to Insufficient data, or no longer in the universe. They stay in your portfolio and return here once scored."
          >
            {unscored.length} not scored: {unscored.join(", ")}
          </span>
        )}
        <span
          className="pfnote"
          title={`${summary.note ? summary.note + " " : ""}${summary.holdings} holdings over ${observations} monthly observation${observations === 1 ? "" : "s"} is a very small sample dominated by noise - these figures describe what happened, they do not establish skill.`}
        >
          {summary.measurable ? `${observations} mo · small sample` : "not measurable yet"}
        </span>
        <SharePortfolioButton />
        <button type="button" className="linkbtn" onClick={clearHoldings}>
          Remove all
        </button>
      </div>

      <RankTable
        rows={heldRows}
        metrics={metrics}
        factors={factors}
        history={history}
        scrollRef={scrollRef}
        tag="pf"
        className="pfwrap"
        showSegment={mixedSegments}
        emptyState={
          <div className="emptyq">
            <strong>None of your holdings has a score this month.</strong>
            They are listed above as not scored, and return here once they are.
          </div>
        }
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
