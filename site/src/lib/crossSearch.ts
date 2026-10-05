import type { ScoresPayload, SegmentKey } from "../data/types";

export const SHOWN_OTHER = 8;

export interface CrossHit {
  ticker: string;
  name: string;
  /** The table the company is in: a segment, or the unranked list. */
  table: SegmentKey | "insufficient";
  rank: number | null;
}

/**
 * Companies matching a search in the tables that are not the one on screen.
 *
 * The table already filters itself, so it is left out here: the point is to find
 * a company that is not in the table the reader happens to be looking at -
 * JPMorgan while Operating is open, or a company that is not ranked at all.
 * Exact ticker first, then tickers that start with the text, then the rest.
 */
export function crossSearch(
  scores: ScoresPayload,
  query: string,
  current: SegmentKey | "insufficient",
  include: "ranked" | "unranked" | "both" = "both",
): CrossHit[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const matches = (ticker: string, name: string) =>
    ticker.toLowerCase().includes(q) || name.toLowerCase().includes(q);
  const hits: CrossHit[] = [];
  for (const [table, rows] of Object.entries(scores.segments) as [SegmentKey, ScoresPayload["segments"][SegmentKey]][]) {
    if (table === current || include === "unranked") continue;
    for (const row of rows) {
      if (matches(row.ticker, row.name)) hits.push({ ticker: row.ticker, name: row.name, table, rank: row.rank });
    }
  }
  if (current !== "insufficient" && include !== "ranked") {
    for (const row of scores.insufficient) {
      if (matches(row.ticker, row.name)) hits.push({ ticker: row.ticker, name: row.name, table: "insufficient", rank: null });
    }
  }
  const order = (h: CrossHit) =>
    h.ticker.toLowerCase() === q ? 0 : h.ticker.toLowerCase().startsWith(q) ? 1 : 2;
  return hits.sort((a, b) => order(a) - order(b) || a.ticker.localeCompare(b.ticker));
}
