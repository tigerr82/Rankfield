import { useMemo, useState, type RefObject } from "react";
import { Link } from "react-router-dom";
import type { FactorSpec, HistoryIndex, MetricSpec, ScoresPayload } from "../data/types";
import type { RankedRow } from "../lib/scoring";
import { monthSummary } from "../lib/monthSummary";
import { COLUMNS, type Column } from "./columns";
import { DeltaCell } from "./cells";
import { RankTable } from "./RankTable";

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
 * place for the full list, and the Rank risers sort already orders it. Each
 * group says what it measures - "climbed most in rank", not "up" - because a
 * bare direction next to a number reads as a price move, which this is not.
 */
interface Props {
  /** The segment's rows, unfiltered: this line describes the month, not a search. */
  rows: RankedRow[];
  scores: ScoresPayload;
  history: HistoryIndex | null;
  metrics: MetricSpec[];
  factors: FactorSpec[];
  scrollRef: RefObject<HTMLElement | null>;
}

/** The same cells as the main table, in a fixed set that explains a move: where
 *  the company stands now, where it stood, and what its price did. Headers do
 *  not sort or resize, so this table never touches the main table's state. */
const MOVER_KEYS = ["_rank", "ticker", "name", "sector", "market_cap", "price", "price_change_pct"];
const MOVER_COLUMNS: Column[] = [
  ...MOVER_KEYS.map((key) => ({ ...COLUMNS.find((c) => c.key === key)!, nosort: true, sticky: false, cls: undefined })),
  {
    key: "_was",
    header: "Last mo.",
    title: "Rank last month",
    align: "r",
    width: 62,
    nosort: true,
    render: (row) => (row.rank_change === null ? "" : (row.rank + row.rank_change).toLocaleString()),
  },
  {
    key: "rank_change",
    header: "Places",
    title: "Places climbed (+) or lost (−) in rank since last month",
    align: "r",
    width: 62,
    nosort: true,
    render: (row) => <DeltaCell value={row.rank_change} digits={0} />,
  },
];

export function MonthSummary({ rows, scores, history, metrics, factors, scrollRef }: Props) {
  const summary = useMemo(() => monthSummary(rows, scores, history), [rows, scores, history]);
  const [open, setOpen] = useState(false);

  if (!summary) return null;

  const month = new Date(`${scores.meta.prior_scoring_date}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });

  const names = (group: RankedRow[]) =>
    group.map((row, i) => (
      <span key={row.ticker}>
        {i > 0 && ", "}
        <Link to={`/stock/${row.ticker}`} className="mosumlink">
          {row.ticker}
        </Link>{" "}
        <span className="mono">{(row.rank_change ?? 0) > 0 ? "+" : ""}{row.rank_change}</span>
      </span>
    ));

  const movers = [...summary.risers, ...summary.fallers];

  return (
    <>
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
      {summary.risers.length > 0 && (
        <span className="mosumgroup" title="The three largest climbs in rank this month, with the number of places gained.">
          climbed most in rank {names(summary.risers)}
        </span>
      )}
      {summary.fallers.length > 0 && (
        <span className="mosumgroup" title="The three largest falls in rank this month, with the number of places lost.">
          fell most in rank {names(summary.fallers)}
        </span>
      )}
    </div>
    {movers.length > 0 && (
      <>
        <button
          type="button"
          className="moverstoggle"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? "▾ Hide" : "▸ Show"} the biggest movers
        </button>
        {open && (
          <RankTable
            rows={movers}
            metrics={metrics}
            factors={factors}
            history={history?.tickers ?? {}}
            scrollRef={scrollRef}
            tag="movers"
            className="moverswrap"
            columns={MOVER_COLUMNS}
          />
        )}
      </>
    )}
    </>
  );
}
