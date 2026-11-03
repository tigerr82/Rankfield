import { describe, expect, it } from "vitest";
import type { HistoryPoint } from "../data/types";
import { stockOutcomes } from "./analytics";
import { comparablePrice } from "./comparablePrice";

const point = (month: string, price: number, price_adj?: number | null): HistoryPoint =>
  ({
    month, composite: 70, rank: 1, price, ...(price_adj === undefined ? {} : { price_adj }),
    factors: null, sector: null, weights_version: "2.4", backtested: false,
  }) as HistoryPoint;

describe("comparable price", () => {
  it("prefers the adjusted price, and falls back to the recorded one only when none exists", () => {
    expect(comparablePrice(point("2026-09", 77.65, 11.65))).toBe(11.65);
    expect(comparablePrice(point("2026-09", 77.65, null))).toBeNull();
    expect(comparablePrice(point("2026-09", 77.65))).toBe(77.65);
  });

  it("does not read a split as a collapse in the per-stock outcomes", () => {
    const history = {
      months: ["2026-07", "2026-08", "2026-09", "2026-10"], observations: 4,
      tickers: {
        AAA: [point("2026-07", 100, 15), point("2026-08", 90, 13.5), point("2026-09", 80, 12), point("2026-10", 15, 15)],
      },
    };
    const [outcome] = stockOutcomes(history, "AAA", 3);
    expect(outcome.ret).toBeCloseTo(0, 5);
  });
});
