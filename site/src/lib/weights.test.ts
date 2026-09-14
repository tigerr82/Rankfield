import { describe, expect, it } from "vitest";
import { DEFAULT_WEIGHTS, FACTOR_ORDER, isDefaultWeights, rebalanceWeights, type Weights } from "./scoring";

const sum = (w: Weights) => Math.round(FACTOR_ORDER.reduce((s, k) => s + w[k], 0) * 100) / 100;

describe("rebalanceWeights", () => {
  it("raising one weight lowers the other three equally, keeping 100", () => {
    const w = rebalanceWeights(DEFAULT_WEIGHTS, "growth", 35);
    expect(w.growth).toBe(35);
    for (const k of ["quality", "valuation", "health"] as const) expect(w[k]).toBeCloseTo(21.67, 1);
    expect(sum(w)).toBe(100);
  });

  it("lowering one weight raises the other three equally", () => {
    const w = rebalanceWeights(DEFAULT_WEIGHTS, "valuation", 10);
    expect(w).toEqual({ quality: 30, growth: 30, valuation: 10, health: 30 });
  });

  it("a weight that reaches zero stops, and the rest absorb the difference equally", () => {
    const start: Weights = { quality: 5, growth: 25, valuation: 35, health: 35 };
    const w = rebalanceWeights(start, "growth", 55);
    expect(w.quality).toBe(0);
    expect(w.valuation).toBe(22.5);
    expect(w.health).toBe(22.5);
    expect(sum(w)).toBe(100);
  });

  it("one factor at 100 leaves the others at zero", () => {
    expect(rebalanceWeights(DEFAULT_WEIGHTS, "quality", 100)).toEqual({ quality: 100, growth: 0, valuation: 0, health: 0 });
  });

  it("clamps the target to 0-100", () => {
    expect(rebalanceWeights(DEFAULT_WEIGHTS, "health", 140).health).toBe(100);
    expect(rebalanceWeights(DEFAULT_WEIGHTS, "health", -20).health).toBe(0);
  });

  it("moving a slider away and back restores the official weighting exactly", () => {
    const away = rebalanceWeights(DEFAULT_WEIGHTS, "growth", 35);
    const back = rebalanceWeights(away, "growth", 25);
    expect(back).toEqual(DEFAULT_WEIGHTS);
    expect(isDefaultWeights(back)).toBe(true);
  });

  it("repairs a total that is not 100 on the next move", () => {
    const broken: Weights = { quality: 25, growth: 35, valuation: 25, health: 25 };
    expect(sum(rebalanceWeights(broken, "quality", 25))).toBe(100);
  });

  it("keeps the total at exactly 100 through any sequence of moves", () => {
    let w: Weights = { ...DEFAULT_WEIGHTS };
    let seed = 7;
    const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < 500; i += 1) {
      const key = FACTOR_ORDER[Math.floor(rand() * 4)];
      w = rebalanceWeights(w, key, Math.round(rand() * 100));
      expect(sum(w)).toBe(100);
      for (const k of FACTOR_ORDER) expect(w[k]).toBeGreaterThanOrEqual(0);
    }
  });
});
