import { describe, expect, it } from "vitest";
import { decileAnalysis, MIN_OBSERVATIONS, summarisePortfolio } from "./analytics";
import type { HistoryIndex, StockRow } from "../data/types";
import type { WatchEvent } from "./portfolio";

function stock(ticker: string, sector: string, changePct: number | null, composite = 50): StockRow {
  return { ticker, name: ticker, sector, composite, price_change_pct: changePct } as StockRow;
}

const WINDOW_START = "2026-07-31T00:00:00Z";
const WINDOW_END = "2026-08-31T00:00:00Z";

const universe = [
  stock("A", "Tech", 10, 80),
  stock("B", "Tech", 6, 60),
  stock("C", "Energy", -4, 40),
  stock("D", "Energy", -6, 30),
];

describe("summarisePortfolio", () => {
  it("excludes positions added after the window opened", () => {
    // The acceptance test for hindsight bias: starring a stock today must not
    // change what the portfolio is reported to have returned last month.
    const held = [stock("A", "Tech", 10, 80)];
    const addedToday: WatchEvent[] = [
      { ticker: "A", added_at: "2026-09-05T00:00:00Z", removed_at: null },
    ];
    const summary = summarisePortfolio(held, universe, addedToday, WINDOW_START, WINDOW_END);
    expect(summary.measurable).toBe(0);
    expect(summary.spread).toBeNull();
    expect(summary.portfolioReturn).toBeNull();
    expect(summary.note).toContain("No position was held");
  });

  it("measures a position that was genuinely held across the window", () => {
    const held = [stock("A", "Tech", 10, 80)];
    const heldThrough: WatchEvent[] = [
      { ticker: "A", added_at: "2026-06-01T00:00:00Z", removed_at: null },
    ];
    const summary = summarisePortfolio(held, universe, heldThrough, WINDOW_START, WINDOW_END);
    expect(summary.measurable).toBe(1);
    expect(summary.portfolioReturn).toBe(10);
    expect(summary.universeReturn).toBe(1.5);  // (10+6-4-6)/4
    expect(summary.spread).toBe(8.5);
  });

  it("separates stock selection from sector allocation", () => {
    // A is +10 against a universe averaging +1.5, but its own sector averages
    // +8 - so most of the raw spread is exposure, not selection.
    const held = [stock("A", "Tech", 10, 80)];
    const events: WatchEvent[] = [{ ticker: "A", added_at: "2026-06-01T00:00:00Z", removed_at: null }];
    const summary = summarisePortfolio(held, universe, events, WINDOW_START, WINDOW_END);
    expect(summary.spread).toBe(8.5);
    expect(summary.sectorAdjustedSpread).toBe(2);  // 10 - 8
    expect(summary.sectorAdjustedSpread!).toBeLessThan(summary.spread!);
  });

  it("benchmarks equal-weighted, matching an equal-weighted watchlist", () => {
    const held = [stock("A", "Tech", 10, 80), stock("D", "Energy", -6, 30)];
    const events: WatchEvent[] = [
      { ticker: "A", added_at: "2026-06-01T00:00:00Z", removed_at: null },
      { ticker: "D", added_at: "2026-06-01T00:00:00Z", removed_at: null },
    ];
    const summary = summarisePortfolio(held, universe, events, WINDOW_START, WINDOW_END);
    expect(summary.portfolioReturn).toBe(2);   // (10 + -6) / 2, not cap-weighted
  });

  it("flags a partially-measurable portfolio rather than silently dropping names", () => {
    const held = [stock("A", "Tech", 10, 80), stock("B", "Tech", 6, 60)];
    const events: WatchEvent[] = [
      { ticker: "A", added_at: "2026-06-01T00:00:00Z", removed_at: null },
      { ticker: "B", added_at: "2026-09-05T00:00:00Z", removed_at: null },
    ];
    const summary = summarisePortfolio(held, universe, events, WINDOW_START, WINDOW_END);
    expect(summary.holdings).toBe(2);
    expect(summary.measurable).toBe(1);
    expect(summary.note).toContain("excluded from the return figures");
  });

  it("handles an empty portfolio without dividing by zero", () => {
    const summary = summarisePortfolio([], universe, [], WINDOW_START, WINDOW_END);
    expect(summary.holdings).toBe(0);
    expect(summary.avgComposite).toBeNull();
    expect(summary.portfolioReturn).toBeNull();
  });

  it("ignores stocks with no price change when averaging", () => {
    const withNulls = [...universe, stock("E", "Tech", null, 50)];
    const held = [stock("A", "Tech", 10, 80)];
    const events: WatchEvent[] = [{ ticker: "A", added_at: "2026-06-01T00:00:00Z", removed_at: null }];
    const summary = summarisePortfolio(held, withNulls, events, WINDOW_START, WINDOW_END);
    expect(summary.universeReturn).toBe(1.5);  // E excluded, not counted as 0
  });
});

describe("decileAnalysis", () => {
  function history(months: number, tickers = 60): HistoryIndex {
    const monthList = Array.from({ length: months }, (_, i) => `2026-${String(i + 1).padStart(2, "0")}`);
    const index: HistoryIndex["tickers"] = {};
    for (let t = 0; t < tickers; t += 1) {
      index[`T${t}`] = monthList.map((month, m) => ({
        month,
        composite: 100 - t,
        rank: t + 1,
        // Higher-scoring names compound faster, so the deciles should separate.
        price: 100 * (1 + (0.01 * (tickers - t)) * m),
        factors: { quality: 100 - t, growth: 100 - t, valuation: 100 - t, health: 100 - t },
        sector: "Tech",
        weights_version: "1.0",
        backtested: false,
      }));
    }
    return { months: monthList, observations: months, tickers: index };
  }

  it("returns all ten deciles so a monotonic progression is visible", () => {
    const result = decileAnalysis(history(8), "composite", "Score", false, 3);
    expect(result.buckets).toHaveLength(10);
    expect(result.buckets.map((b) => b.decile)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });

  it("detects a monotonic relationship when one exists", () => {
    const result = decileAnalysis(history(8), "composite", "Score", false, 3);
    expect(result.monotonic).toBe(true);
    expect(result.topSpread).toBeGreaterThan(0);
  });

  it("refuses to call a short sample interpretable", () => {
    const result = decileAnalysis(history(5), "composite", "Score", false, 3);
    expect(result.observations).toBeLessThan(MIN_OBSERVATIONS);
    expect(result.interpretable).toBe(false);
  });

  it("marks a sample interpretable only past the observation floor", () => {
    const result = decileAnalysis(history(MIN_OBSERVATIONS + 4), "composite", "Score", false, 3);
    expect(result.observations).toBeGreaterThanOrEqual(MIN_OBSERVATIONS);
    expect(result.interpretable).toBe(true);
  });

  it("produces an empty, non-crashing result on a single month", () => {
    const result = decileAnalysis(history(1), "composite", "Score", false, 3);
    expect(result.observations).toBe(0);
    expect(result.interpretable).toBe(false);
    expect(result.buckets.every((b) => b.meanForwardReturn === null)).toBe(true);
  });

  it("handles an entirely empty history", () => {
    const empty: HistoryIndex = { months: [], observations: 0, tickers: {} };
    const result = decileAnalysis(empty, "composite", "Score", false, 3);
    expect(result.observations).toBe(0);
    expect(result.universeMean).toBeNull();
  });

  it("carries the price-contamination flag through to the result", () => {
    const result = decileAnalysis(history(8), "valuation", "Value", true, 3);
    expect(result.priceDependent).toBe(true);
  });
});
