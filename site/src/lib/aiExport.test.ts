import { describe, expect, it } from "vitest";
import type { ScoresPayload, StockRow } from "../data/types";
import { companyPrompt, packMetricLines, selectionPrompt, tablePrompt, TABLE_ROWS } from "./aiExport";

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

  it("copies every table in turn, the limit applying to each table on its own", () => {
    const two = {
      ...payload,
      segments_meta: [...payload.segments_meta, { key: "banks", label: "Banks" }],
      segments: { operating: rows, banks: [row(1, "B1"), row(2, "B2")] },
    } as unknown as ScoresPayload;
    const text = tablePrompt(two, "all", 10);
    expect(text).toContain("Table: Operating companies. The top 10 of 150");
    expect(text).toContain("Table: Banks. All 2 companies");
    expect(text.split(/\r?\n/).filter((l) => /^\d+ \| (T|B)/.test(l))).toHaveLength(12);
    expect(text.match(/Method:/g)).toHaveLength(1);
  });

  it("copies a selection over time, with the latest metrics on request", () => {
    const point = (month: string, composite: number, rank: number, price: number, q: number) => ({
      month, composite, rank, price, factors: { quality: q, growth: q + 1, valuation: q + 2, health: q + 3 },
      sector: "Tech", weights_version: "2.4", backtested: false,
    });
    const history = {
      months: ["2026-09", "2026-10"], observations: 2,
      tickers: { T1: [point("2026-09", 80, 3, 9, 1), point("2026-10", 89, 1, 10, 5)] },
    };
    const text = selectionPrompt(payload, history, { tickers: ["t1", "zzz"], months: 1, depth: "latest" });
    expect(text).toContain("2026-10 | 1 | 89.0 | 5 | 6 | 7 | 8 | 10 | 2.4");
    expect(text).not.toContain("2026-09 |");
    expect(text).toContain("ROE [quality]: 25.0%");
    expect(text).toContain("Not found in the ranked tables: ZZZ");
  });

  it("reads every month of a metric from the data pack, grouped so a trend is one line", () => {
    const csv = [
      "month,ticker,metric,factor,raw_value,sector_percentile,basis",
      "2026-09,T1,roe,quality,0.2,80.0,sector",
      "2026-10,T1,roe,quality,0.25,91.0,sector",
      "2026-10,T2,roe,quality,0.1,10.0,sector",
    ].join("\n");
    const lines = packMetricLines(csv, payload, ["t1"], null);
    expect(lines.get("T1")).toEqual(["  ROE [quality]: 2026-09 20.0% (p80) | 2026-10 25.0% (p91)"]);
    expect(lines.has("T2")).toBe(false);
    const text = selectionPrompt(payload, undefined, { tickers: ["T1"], months: null, depth: "full" }, lines);
    expect(text).toContain("2026-09 20.0% (p80) | 2026-10 25.0% (p91)");
    expect(packMetricLines(csv, payload, ["T1"], ["2026-10"]).get("T1")![0]).not.toContain("2026-09");
  });

  it("copies one company with its metrics and rank", () => {
    const text = companyPrompt(payload, rows.find((r) => r.ticker === "T1")!);
    expect(text).toContain("T1 - T1 Inc");
    expect(text).toContain("rank 1 of 150");
    expect(text).toContain("ROE: 25.0%");
    expect(text).toContain("since last month +3");
  });
});
