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
  return weightsEqual(weights, DEFAULT_WEIGHTS);
}

export function weightsEqual(a: Weights, b: Weights): boolean {
  // Rebalanced weights are fractional (a 10-point move shifts the other three by
  // 3.33 each), so compare to the hundredth rather than exactly.
  return FACTOR_ORDER.every((k) => Math.abs((a[k] ?? 0) - (b[k] ?? 0)) < 0.005);
}

/** "25" for whole weights, "21.7" otherwise. */
export function formatWeight(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/**
 * Set one factor's weight and move the other three to keep the total at 100.
 *
 * The difference is split equally across the other factors. A factor that
 * reaches 0 stops there - a weight cannot go negative - and the factors still
 * above 0 absorb the rest, again equally. Arithmetic is done in hundredths of a
 * percent so the total is exactly 100, and a leftover hundredth always goes to
 * the same factor, so moving a slider away and back returns every weight to
 * where it started.
 */
export function rebalanceWeights(weights: Weights, key: FactorKey, target: number): Weights {
  const TOTAL = 10000;
  const cents = (v: number) => Math.round((Number.isFinite(v) ? v : 0) * 100);
  const next = {} as Record<FactorKey, number>;
  for (const k of FACTOR_ORDER) next[k] = Math.max(0, cents(weights[k] ?? 0));
  next[key] = Math.max(0, Math.min(TOTAL, cents(target)));

  const others = FACTOR_ORDER.filter((k) => k !== key);
  let remaining = TOTAL - next[key] - others.reduce((sum, k) => sum + next[k], 0);

  while (remaining !== 0) {
    const shrinking = remaining < 0;
    const active = others.filter((k) => !shrinking || next[k] > 0);
    if (!active.length) break;
    const share = Math.trunc(remaining / active.length);
    let leftover = remaining - share * active.length;
    let moved = 0;
    for (const k of active) {
      let step = share;
      if (leftover !== 0) {
        step += Math.sign(leftover);
        leftover -= Math.sign(leftover);
      }
      if (shrinking) step = Math.max(step, -next[k]);
      next[k] += step;
      moved += step;
    }
    remaining -= moved;
    if (moved === 0) break;
  }

  const out = {} as Weights;
  for (const k of FACTOR_ORDER) out[k] = next[k] / 100;
  return out;
}

/**
 * The composite to display for a row.
 *
 * At the official weighting this returns the STORED value instead of
 * recomputing it. Python writes the published payload and the append-only
 * history; re-deriving the same figure here disagreed with it on 22% of rows,
 * because Python rounds half-to-even on the exact double while JavaScript
 * rounds half away from zero after a multiplication that is itself lossy. The
 * browser must never contradict the record it was given.
 *
 * Only a what-if weighting is computed live - that value is exploratory, is
 * labelled as such, and is never stored.
 */
export function displayComposite(
  row: Pick<StockRow, "composite" | "factors">,
  weights: Weights,
  official?: Weights,
): number | null {
  if (official && weightsEqual(weights, official)) return row.composite;
  return compositeOf(row.factors, weights);
}

export interface RankedRow extends StockRow {
  /** Composite under the currently active weights - equals `composite` at the
   *  official weighting. */
  liveComposite: number | null;
  liveRank: number;
}

/** Re-rank a segment under arbitrary weights. Rows with no composite sort last.
 *  Pass `official` (from the payload meta) so the official weighting shows the
 *  stored figures rather than recomputed ones. */
export function rankRows(rows: StockRow[], weights: Weights, official?: Weights): RankedRow[] {
  const out = rows.map((row) => ({
    ...row,
    liveComposite: displayComposite(row, weights, official),
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
export function rankDisplacement(rows: StockRow[], weights: Weights, official?: Weights): number {
  const reference = official ?? DEFAULT_WEIGHTS;
  const base = rankRows(rows, reference, official).map((r) => r.ticker);
  const now = rankRows(rows, weights, official).map((r) => r.ticker);
  let moved = 0;
  for (let i = 0; i < base.length; i += 1) if (base[i] !== now[i]) moved += 1;
  return moved;
}
