import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { HistoryIndex, ScoresPayload, StockRow } from "../data/types";
import { monthSummary } from "../lib/monthSummary";

/**
 * What changed in this table since last month, in one line.
 *
 * Every piece of it was already on the page and nowhere a reader would look:
 * the rank change sits in a column that has to be sorted on, a company scored
 * for the first time is indistinguishable from one that climbed 500 places, and
 * a company that left the ranking simply vanishes. One line above the table
 * answers "what happened this month" without the reader having to interrogate
 * it.
 *
 * Three names per direction: a line that reads at a glance. The table is the
 * place for the full list, and the Rank risers sort already orders it.
 */
interface Props {
  /** The segment's rows, unfiltered: this line describes the month, not a search. */
  rows: StockRow[];
  scores: ScoresPayload;
  history: HistoryIndex | null;
}

export function MonthSummary({ rows, scores, history }: Props) {
  const summary = useMemo(() => monthSummary(rows, scores, history), [rows, scores, history]);

  if (!summary) return null;

  const month = new Date(`${scores.meta.prior_scoring_date}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });

  const names = (group: StockRow[]) =>
    group.map((row, i) => (
      <span key={row.ticker}>
        {i > 0 && ", "}
        <Link to={`/stock/${row.ticker}`} className="mosumlink">
          {row.ticker}
        </Link>{" "}
        <span className="mono">{(row.rank_change ?? 0) > 0 ? "+" : ""}{row.rank_change}</span>
      </span>
    ));

  return (
    <div className="mosum" role="note">
      <span className="mosumlabel">Since {month}</span>
      {summary.entered > 0 && (
        <span title="Scored for the first time this month: no rank to move from.">
          <b>{summary.entered.toLocaleString()}</b> newly scored
        </span>
      )}
      {summary.left > 0 && (
        <span title="Scored last month and not this month - usually the market-cap, liquidity or filing filters, sometimes a metric that stopped resolving. The Coverage page lists every exclusion.">
          <b>{summary.left.toLocaleString()}</b> left the ranking
        </span>
      )}
      {summary.typical !== null && (
        <span title="Half of the companies in this table moved less than this. A small figure is the point: a ranking that reshuffles every month is measuring noise.">
          typical move <b>{summary.typical.toLocaleString()}</b> places
        </span>
      )}
      {summary.risers.length > 0 && <span className="mosumgroup">up {names(summary.risers)}</span>}
      {summary.fallers.length > 0 && <span className="mosumgroup">down {names(summary.fallers)}</span>}
    </div>
  );
}
