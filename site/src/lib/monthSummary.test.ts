import { describe, expect, it } from "vitest";
import { monthSummary } from "./monthSummary";
import type { HistoryIndex, ScoresPayload, StockRow } from "../data/types";

/**
 * The line above the table is the only place the month-over-month story is
 * told, so the arithmetic behind it is worth pinning: a first appearance is not
 * a 500-place climb, and a company that left has to be found in the history
 * because it is no longer in the payload at all.
 */
const row = (ticker: string, rank_change: number | null, is_new = false) =>
  ({ ticker, rank_change, is_new, rank: 1, composite: 50 } as unknown as StockRow);

const payload = (tickers: string[]) =>
  ({ segments: { operating: tickers.map((t) => row(t, 0)) } } as unknown as ScoresPayload);

const history = (months: string[], tickers: Record<string, string[]>) =>
  ({
    months,
    tickers: Object.fromEntries(
      Object.entries(tickers).map(([t, ms]) => [t, ms.map((month) => ({ month }))]),
    ),
  } as unknown as HistoryIndex);

describe("monthSummary", () => {
  const rows = [
    row("UP1", 585), row("UP2", 300), row("UP3", 120), row("UP4", 40),
    row("DOWN1", -698), row("DOWN2", -400), row("DOWN3", -90),
    row("FLAT", 0), row("FRESH", null, true),
  ];
  const scores = payload(["UP1", "UP2", "UP3", "UP4", "DOWN1", "DOWN2", "DOWN3", "FLAT", "FRESH"]);
  const hist = history(["2026-08", "2026-09"], {
    UP1: ["2026-08", "2026-09"],
    GONE: ["2026-08"],
    LONGGONE: ["2026-07"],
  });

  it("says nothing in the first month, when there is nothing to compare", () => {
    expect(monthSummary(rows, scores, history(["2026-08"], {}))).toBeNull();
    expect(monthSummary(rows, scores, null)).toBeNull();
  });

  it("names the three biggest climbs, largest first", () => {
    expect(monthSummary(rows, scores, hist)!.risers.map((r) => r.ticker)).toEqual(["UP1", "UP2", "UP3"]);
  });

  it("names the three biggest falls, largest first", () => {
    expect(monthSummary(rows, scores, hist)!.fallers.map((r) => r.ticker)).toEqual(["DOWN1", "DOWN2", "DOWN3"]);
  });

  it("counts a first appearance separately instead of ranking it as a climb", () => {
    const summary = monthSummary(rows, scores, hist)!;
    expect(summary.entered).toBe(1);
    expect([...summary.risers, ...summary.fallers].map((r) => r.ticker)).not.toContain("FRESH");
  });

  it("counts only companies that were scored last month and are not scored now", () => {
    // GONE had a record last month and is absent now; LONGGONE left earlier and
    // is not news this month; UP1 is still here.
    expect(monthSummary(rows, scores, hist)!.left).toBe(1);
  });

  it("reports the typical move as the median of actual moves, ignoring the unmoved", () => {
    // |585, 300, 120, 40, 698, 400, 90| -> median 300
    expect(monthSummary(rows, scores, hist)!.typical).toBe(300);
  });

  it("holds up when nothing moved at all", () => {
    const still = [row("A", 0), row("B", 0)];
    const summary = monthSummary(still, payload(["A", "B"]), hist)!;
    expect(summary.typical).toBeNull();
    expect(summary.risers).toEqual([]);
    expect(summary.fallers).toEqual([]);
  });
});
