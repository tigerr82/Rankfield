import { describe, expect, it } from "vitest";
import type { ScoresPayload, StockRow } from "../data/types";
import { companyPrompt, tablePrompt, TABLE_ROWS } from "./aiExport";

const row = (rank: number, ticker: string): StockRow =>
  ({
    ticker, name: `${ticker} Inc`, sector: "Tech", peer_group: null, segment: "operating",
    rank, composite: 90 - rank, factors: { quality: 80, growth: 70, valuation: 60, health: 50 },
    metrics: { roe: { raw: 0.25, pct: 91, basis: null } }, rank_change: rank === 1 ? 3 : -2,
    price: 10, price_change_pct: 1.5, fundamentals_asof: "2026-06-30", form: "10-Q", filed: "2026-07-30",
  }) as unknown as StockRow;

const rows = Array.from({ length: 150 }, (_, i) => row(i + 1, `T${i + 1}`)).reverse();

const payload = {
  meta: { scoring_date: "2026-10-31", weights_version: "2.4" },
  segments_meta: [{ key: "operating", label: "Operating companies" }],
  metrics: [{ key: "roe", label: "ROE", factor: "quality", unit: "pct" }],
  factors: [{ key: "quality", label: "Quality" }, { key: "growth", label: "Growth" },
    { key: "valuation", label: "Value" }, { key: "health", label: "Health" }],
  segments: { operating: rows },
  insufficient: [],
} as unknown as ScoresPayload;

describe("AI export", () => {
  it("copies the best rows of a table in rank order and says how many were left out", () => {
    const text = tablePrompt(payload, "operating");
    const body = text.split("\n").filter((l) => /^\d+ \| T/.test(l));
    expect(body).toHaveLength(TABLE_ROWS);
    expect(body[0].startsWith("1 | T1 |")).toBe(true);
    expect(text).toContain(`top ${TABLE_ROWS} of 150`);
    expect(text).toContain("Not investment advice");
  });

  it("copies the whole table when no limit is given", () => {
    const text = tablePrompt(payload, "operating", null);
    expect(text.split(/\r?\n/).filter((l) => /^\d+ \| T/.test(l))).toHaveLength(150);
    expect(text).toContain("All 150 companies");
  });

  it("copies one company with its metrics and rank", () => {
    const text = companyPrompt(payload, rows.find((r) => r.ticker === "T1")!);
    expect(text).toContain("T1 - T1 Inc");
    expect(text).toContain("rank 1 of 150");
    expect(text).toContain("ROE: 25.0%");
    expect(text).toContain("since last month +3");
  });
});
