/**
 * The two analysis surfaces: does the score predict anything, and is the user's
 * own selection beating the field?
 *
 * Both are easy to get confidently wrong, so the rules are enforced here rather
 * than left to the components:
 *
 *  - Level to forward return, never change against change. Contemporaneous
 *    co-movement of score and price is not actionable.
 *  - Report per factor, not only on the composite. Quality, Growth and Financial
 *    Health are price-independent; Value contains price by construction, so its
 *    correlation with price is arithmetic and is labelled as such everywhere.
 *  - Benchmark everything and expose the sample size. Below MIN_OBSERVATIONS
 *    monthly observations the UI must say the sample is too small, never render
 *    a figure that implies significance it does not have.
 *  - The portfolio benchmark is equal-weighted, because a v1 watchlist is
 *    equal-weighted. Comparing an equal-weighted portfolio against a
 *    cap-weighted benchmark manufactures performance out of the mismatch alone.
 */
import type { FactorKey, HistoryIndex, StockRow } from "../data/types";
import { heldOn, type WatchEvent } from "./portfolio";

/** Below this many monthly observations, no result is presented as evidence. */
export const MIN_OBSERVATIONS = 12;

const mean = (xs: number[]): number | null =>
  xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;

// ------------------------------------------------------------- portfolio

export interface HoldingLine {
  ticker: string;
  name: string;
  sector: string | null;
  composite: number | null;
  changePct: number | null;
  sectorAvg: number | null;
  /** change minus the stock's own sector average - selection, not allocation */
  sectorAdjusted: number | null;
  heldAtWindowStart: boolean;
}

export interface PortfolioSummary {
  holdings: number;
  avgComposite: number | null;
  avgChange: number | null;
  /** Measured only over positions actually held at the window start. */
  measurable: number;
  windowStart: string;
  windowEnd: string;
  portfolioReturn: number | null;
  universeReturn: number | null;
  spread: number | null;
  sectorAdjustedSpread: number | null;
  universeAvgComposite: number | null;
  lines: HoldingLine[];
  /** Why a figure is missing, when it is. */
  note: string | null;
}

export function summarisePortfolio(
  held: StockRow[],
  universe: StockRow[],
  events: WatchEvent[],
  windowStart: string,
  windowEnd: string,
): PortfolioSummary {
  const sectorAverages = new Map<string, number>();
  const bySector = new Map<string, number[]>();
  for (const row of universe) {
    if (row.price_change_pct == null) continue;
    const key = row.sector ?? "(unclassified)";
    if (!bySector.has(key)) bySector.set(key, []);
    bySector.get(key)!.push(row.price_change_pct);
  }
  for (const [key, values] of bySector) {
    const m = mean(values);
    if (m != null) sectorAverages.set(key, m);
  }

  const lines: HoldingLine[] = held.map((row) => {
    const sectorAvg = sectorAverages.get(row.sector ?? "(unclassified)") ?? null;
    return {
      ticker: row.ticker,
      name: row.name,
      sector: row.sector,
      composite: row.composite,
      changePct: row.price_change_pct,
      sectorAvg,
      sectorAdjusted:
        row.price_change_pct != null && sectorAvg != null ? row.price_change_pct - sectorAvg : null,
      // The hindsight guard: starring a stock today must not change what the
      // portfolio is reported to have returned over a window that has closed.
      heldAtWindowStart: heldOn(row.ticker, windowStart, events),
    };
  });

  const measurable = lines.filter((l) => l.heldAtWindowStart && l.changePct != null);
  const universeChanges = universe
    .map((r) => r.price_change_pct)
    .filter((v): v is number => v != null);
  const universeReturn = mean(universeChanges);

  const portfolioReturn = mean(measurable.map((l) => l.changePct!));
  const sectorAdjustedSpread = mean(
    measurable.map((l) => l.sectorAdjusted).filter((v): v is number => v != null),
  );

  let note: string | null = null;
  if (!held.length) note = null;
  else if (!measurable.length) {
    note = `No position was held on ${windowStart}, so there is no return to measure for this window yet. Figures appear once a position has been held across a full scoring period.`;
  } else if (measurable.length < held.length) {
    note = `${held.length - measurable.length} of ${held.length} holdings were added after ${windowStart} and are excluded from the return figures - counting them would credit gains that were never captured.`;
  }

  return {
    holdings: held.length,
    avgComposite: mean(held.map((r) => r.composite).filter((v): v is number => v != null)),
    avgChange: mean(held.map((r) => r.price_change_pct).filter((v): v is number => v != null)),
    measurable: measurable.length,
    windowStart,
    windowEnd,
    portfolioReturn,
    universeReturn,
    spread:
      portfolioReturn != null && universeReturn != null ? portfolioReturn - universeReturn : null,
    sectorAdjustedSpread,
    universeAvgComposite: mean(
      universe.map((r) => r.composite).filter((v): v is number => v != null),
    ),
    lines,
    note,
  };
}

// ------------------------------------------------------ score vs. price

export interface DecileBucket {
  decile: number;          // 1 = highest scoring
  meanForwardReturn: number | null;
  count: number;
}

export interface ValidationResult {
  key: "composite" | FactorKey;
  label: string;
  priceDependent: boolean;
  horizonMonths: number;
  observations: number;    // number of distinct start months
  sampleSize: number;      // stock-months underlying the result
  buckets: DecileBucket[];
  universeMean: number | null;
  topSpread: number | null;
  monotonic: boolean;
  interpretable: boolean;  // false below MIN_OBSERVATIONS
}

function scoreAt(point: { composite: number | null; factors?: Record<string, number | null> | null },
                 key: "composite" | FactorKey): number | null {
  if (key === "composite") return point.composite;
  return point.factors?.[key] ?? null;
}

/**
 * Bucket stocks by their score at month T and measure the return realised over
 * the following `horizon` months. All ten deciles are returned: a clean
 * monotonic progression is what makes a result credible, and its absence is
 * itself informative.
 */
export function decileAnalysis(
  history: HistoryIndex,
  key: "composite" | FactorKey,
  label: string,
  priceDependent: boolean,
  horizon = 3,
): ValidationResult {
  const months = history.months;
  const sums = Array.from({ length: 10 }, () => ({ total: 0, n: 0 }));
  const allReturns: number[] = [];
  let observations = 0;

  for (let i = 0; i + horizon < months.length; i += 1) {
    const from = months[i];
    const to = months[i + horizon];
    const pairs: { score: number; ret: number }[] = [];

    for (const points of Object.values(history.tickers)) {
      const a = points.find((p) => p.month === from);
      const b = points.find((p) => p.month === to);
      if (!a || !b || a.price == null || b.price == null || a.price <= 0) continue;
      const score = scoreAt(a, key);
      if (score == null) continue;
      pairs.push({ score, ret: (b.price / a.price - 1) * 100 });
    }
    if (pairs.length < 30) continue;

    observations += 1;
    pairs.sort((x, y) => y.score - x.score);
    const size = pairs.length / 10;
    pairs.forEach((p, idx) => {
      const bucket = Math.min(9, Math.floor(idx / size));
      sums[bucket].total += p.ret;
      sums[bucket].n += 1;
      allReturns.push(p.ret);
    });
  }

  const buckets: DecileBucket[] = sums.map((s, i) => ({
    decile: i + 1,
    meanForwardReturn: s.n ? s.total / s.n : null,
    count: s.n,
  }));
  const universeMean = mean(allReturns);
  const top = buckets[0].meanForwardReturn;
  const values = buckets.map((b) => b.meanForwardReturn).filter((v): v is number => v != null);
  const monotonic =
    values.length === 10 && values.every((v, i) => i === 0 || v <= values[i - 1] + 1e-9);

  return {
    key,
    label,
    priceDependent,
    horizonMonths: horizon,
    observations,
    sampleSize: allReturns.length,
    buckets,
    universeMean,
    topSpread: top != null && universeMean != null ? top - universeMean : null,
    monotonic,
    interpretable: observations >= MIN_OBSERVATIONS,
  };
}

/** Per-stock outcome pairs. Illustrative only: one stock over one period is a
 *  single noisy observation and cannot validate or refute the method. */
export function stockOutcomes(history: HistoryIndex, ticker: string, horizon = 3) {
  const points = history.tickers[ticker] ?? [];
  const out: { from: string; to: string; score: number; ret: number }[] = [];
  for (let i = 0; i + horizon < points.length; i += 1) {
    const a = points[i];
    const b = points[i + horizon];
    if (a.composite == null || a.price == null || b.price == null || a.price <= 0) continue;
    out.push({ from: a.month, to: b.month, score: a.composite, ret: (b.price / a.price - 1) * 100 });
  }
  return out;
}
