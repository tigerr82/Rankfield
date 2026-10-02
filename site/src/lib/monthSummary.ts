import type { HistoryIndex, ScoresPayload, StockRow } from "../data/types";

/** Three names per direction: a line that reads at a glance. The table is the
 *  place for the full list, and the Rank risers sort already orders it. */
export const SHOWN = 3;

export interface MonthSummary<T extends StockRow = StockRow> {
  entered: number;
  left: number;
  typical: number | null;
  risers: T[];
  fallers: T[];
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * What changed in this table since last month.
 *
 * `rank_change` is last month's rank minus this month's, so a climb is
 * positive. A company scored for the first time has no rank to move from and is
 * counted separately rather than ranked among the risers - otherwise a first
 * appearance would top the list every month.
 *
 * Companies that left are not in the payload at all; they are found by asking
 * the history index who had a record last month and has none now.
 */
export function monthSummary<T extends StockRow>(
  rows: T[],
  scores: ScoresPayload,
  history: HistoryIndex | null,
): MonthSummary<T> | null {
  if (!history || history.months.length < 2) return null;
  const changed = rows.filter(
    (r) => !r.is_new && typeof r.rank_change === "number" && r.rank_change !== 0,
  );
  const byMove = (a: T, b: T) => (b.rank_change ?? 0) - (a.rank_change ?? 0);
  const scoredNow = new Set<string>();
  for (const segment of Object.values(scores.segments)) {
    for (const row of segment) scoredNow.add(row.ticker);
  }
  const previous = history.months[history.months.length - 2];
  const left = Object.entries(history.tickers).filter(
    ([ticker, points]) => !scoredNow.has(ticker) && points.some((p) => p.month === previous),
  ).length;
  return {
    entered: rows.filter((r) => r.is_new).length,
    left,
    typical: median(changed.map((r) => Math.abs(r.rank_change ?? 0))),
    risers: [...changed].sort(byMove).slice(0, SHOWN).filter((r) => (r.rank_change ?? 0) > 0),
    fallers: [...changed].sort((a, b) => byMove(b, a)).slice(0, SHOWN).filter((r) => (r.rank_change ?? 0) < 0),
  };
}
