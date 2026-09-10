/**
 * Client-side re-weighting.
 *
 * Factor percentiles are precomputed and shipped in the payload, so recomputing
 * the composite under different weights is a weighted average of numbers that
 * are already in the browser. It must never trigger a re-run, a refetch or a
 * server call - and it never writes to history: what-if weights are session
 * state, and the stored monthly scores keep the official weights that produced
 * them.
 *
 * This mirrors `composite_of` in scripts/rankfield/scoring.py. The two must
 * agree, or the table would disagree with the stored ranks at default weights.
 */
import type { FactorKey, StockRow } from "../data/types";

export const FACTOR_ORDER: FactorKey[] = ["quality", "growth", "valuation", "health"];
export const DEFAULT_WEIGHTS: Record<FactorKey, number> = {
  quality: 25,
  growth: 25,
  valuation: 25,
  health: 25,
};

export type Weights = Record<FactorKey, number>;

export function compositeOf(
  factors: Record<FactorKey, number | null>,
  weights: Weights,
): number | null {
  let total = 0;
  let weight = 0;
  for (const key of FACTOR_ORDER) {
    const value = factors[key];
    const w = weights[key] ?? 0;
    if (value != null && w > 0) {
      total += value * w;
      weight += w;
    }
  }
  return weight ? Math.round((total / weight) * 100) / 100 : null;
}

export function isDefaultWeights(weights: Weights): boolean {
  return FACTOR_ORDER.every((k) => weights[k] === DEFAULT_WEIGHTS[k]);
}

export interface RankedRow extends StockRow {
  /** Composite under the currently active weights - equals `composite` at the
   *  official weighting. */
  liveComposite: number | null;
  liveRank: number;
}

/** Re-rank a segment under arbitrary weights. Rows with no composite sort last. */
export function rankRows(rows: StockRow[], weights: Weights): RankedRow[] {
  const out = rows.map((row) => ({
    ...row,
    liveComposite: compositeOf(row.factors, weights),
  })) as RankedRow[];
  out.sort((a, b) => {
    if (a.liveComposite == null) return b.liveComposite == null ? 0 : 1;
    if (b.liveComposite == null) return -1;
    return b.liveComposite - a.liveComposite;
  });
  out.forEach((row, i) => {
    row.liveRank = i + 1;
  });
  return out;
}

/** How many stocks the current weighting moves relative to the official one. */
export function rankDisplacement(rows: StockRow[], weights: Weights): number {
  const base = rankRows(rows, DEFAULT_WEIGHTS).map((r) => r.ticker);
  const now = rankRows(rows, weights).map((r) => r.ticker);
  let moved = 0;
  for (let i = 0; i < base.length; i += 1) if (base[i] !== now[i]) moved += 1;
  return moved;
}
