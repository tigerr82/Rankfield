import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { compositeOf, DEFAULT_WEIGHTS, displayComposite, isDefaultWeights, rankDisplacement, rankRows } from "./scoring";
import type { FactorKey, StockRow } from "../data/types";

const EQUAL = DEFAULT_WEIGHTS;

function row(factors: Partial<Record<FactorKey, number | null>>, ticker = "X"): StockRow {
  return {
    ticker,
    factors: { quality: null, growth: null, valuation: null, health: null, ...factors },
  } as StockRow;
}

describe("compositeOf", () => {
  it("averages the factors at equal weights", () => {
    expect(compositeOf({ quality: 80, growth: 60, valuation: 40, health: 20 }, EQUAL)).toBe(50);
  });

  it("renormalises around a missing factor instead of scoring it zero", () => {
    const renormalised = compositeOf({ quality: 80, growth: 60, valuation: 40, health: null }, EQUAL);
    const imputedAsZero = compositeOf({ quality: 80, growth: 60, valuation: 40, health: 0 }, EQUAL);
    expect(renormalised).toBe(60);
    expect(imputedAsZero).toBe(45);
  });

  it("returns null when every factor is missing", () => {
    expect(compositeOf({ quality: null, growth: null, valuation: null, health: null }, EQUAL)).toBeNull();
  });

  it("returns null rather than dividing by zero when all weights are zero", () => {
    expect(
      compositeOf({ quality: 70, growth: 10, valuation: 10, health: 10 },
        { quality: 0, growth: 0, valuation: 0, health: 0 }),
    ).toBeNull();
  });

  it("ignores zero-weighted factors", () => {
    expect(
      compositeOf({ quality: 70, growth: 10, valuation: 10, health: 10 },
        { quality: 100, growth: 0, valuation: 0, health: 0 }),
    ).toBe(70);
  });
});

/**
 * The cross-language contract.
 *
 * `compositeOf` here and `composite_of` in scripts/rankfield/scoring.py are two
 * implementations of one formula. If they drift, the browser silently shows
 * different numbers from the ones written into the append-only history - and
 * the divergence would never surface as an error.
 */
describe("parity with the Python scorer", () => {
  const payload = JSON.parse(readFileSync(new URL("../../public/data/scores_full.json", import.meta.url), "utf-8"));
  const rows: StockRow[] = Object.values(payload.segments as Record<string, StockRow[]>).flat();

  it("has rows to check", () => {
    expect(rows.length).toBeGreaterThan(1000);
  });

  it("displays exactly the stored composite at the official weights", () => {
    const official = payload.meta.weights as Record<FactorKey, number>;
    const mismatches = rows
      .map((r) => ({ ticker: r.ticker, stored: r.composite, shown: displayComposite(r, official, official) }))
      .filter((x) => x.stored !== x.shown);
    expect(mismatches.slice(0, 10)).toEqual([]);
  });

  it("reproduces the stored rank ordering at the official weights", () => {
    const official = payload.meta.weights as Record<FactorKey, number>;
    const operating = payload.segments.operating as StockRow[];
    const ranked = rankRows(operating, official, official);
    // Ties are legitimate (winsorization collapses the tail), so compare the
    // composite sequence rather than demanding identical tie ordering.
    expect(ranked.map((r) => r.liveComposite)).toEqual(operating.map((r) => r.composite));
  });

  it("would disagree with the record if it recomputed instead - which is why it does not", () => {
    // Python rounds half-to-even on the exact double; JavaScript rounds half
    // away from zero after a lossy multiply. Recomputing published figures in
    // the browser diverged on roughly a fifth of rows by 0.01. This test pins
    // the reason `displayComposite` prefers the stored value, so that anyone
    // "simplifying" it back to a recompute sees the cost immediately.
    const official = payload.meta.weights as Record<FactorKey, number>;
    const recomputed = rows.filter((r) => compositeOf(r.factors, official) !== r.composite);
    expect(recomputed.length).toBeGreaterThan(0);
    for (const r of recomputed) {
      expect(Math.abs(compositeOf(r.factors, official)! - r.composite!)).toBeLessThanOrEqual(0.011);
      // ...and the displayed value still matches the record exactly.
      expect(displayComposite(r, official, official)).toBe(r.composite);
    }
  });
});

describe("rankRows", () => {
  it("orders by composite descending and numbers from one", () => {
    const ranked = rankRows(
      [row({ quality: 10 }, "LOW"), row({ quality: 90 }, "HIGH"), row({ quality: 50 }, "MID")],
      EQUAL,
    );
    expect(ranked.map((r) => r.ticker)).toEqual(["HIGH", "MID", "LOW"]);
    expect(ranked.map((r) => r.liveRank)).toEqual([1, 2, 3]);
  });

  it("sorts unscored rows last in both directions", () => {
    const ranked = rankRows([row({}, "NONE"), row({ quality: 50 }, "SOME")], EQUAL);
    expect(ranked[0].ticker).toBe("SOME");
    expect(ranked[1].liveComposite).toBeNull();
  });

  it("does not mutate the input array", () => {
    const input = [row({ quality: 10 }, "A"), row({ quality: 90 }, "B")];
    rankRows(input, EQUAL);
    expect(input.map((r) => r.ticker)).toEqual(["A", "B"]);
  });

  it("handles an empty table", () => {
    expect(rankRows([], EQUAL)).toEqual([]);
  });
});

describe("weight helpers", () => {
  it("recognises the official weighting", () => {
    expect(isDefaultWeights(EQUAL)).toBe(true);
    expect(isDefaultWeights({ ...EQUAL, quality: 55 })).toBe(false);
  });

  it("reports no displacement at the default weighting", () => {
    const rows = [row({ quality: 90, growth: 10 }, "A"), row({ quality: 10, growth: 90 }, "B")];
    expect(rankDisplacement(rows, EQUAL)).toBe(0);
  });

  it("reports displacement when a weight actually reorders the table", () => {
    const rows = [row({ quality: 90, growth: 10 }, "A"), row({ quality: 10, growth: 90 }, "B")];
    expect(rankDisplacement(rows, { quality: 0, growth: 100, valuation: 0, health: 0 })).toBeGreaterThan(0);
  });
});
