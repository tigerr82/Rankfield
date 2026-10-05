import { describe, expect, it } from "vitest";
import type { ScoresPayload } from "../data/types";
import { crossSearch } from "./crossSearch";

const row = (ticker: string, name: string, rank = 1) => ({ ticker, name, rank });
const scores = {
  segments: {
    operating: [row("AAPL", "Apple Inc."), row("JPMX", "Jpm Holdings Operating")],
    financials: [row("JPM", "JPMorgan Chase & Co."), row("BAC", "Bank of America")],
    reits: [row("PLD", "Prologis")],
    pre_revenue: [],
  },
  insufficient: [{ ticker: "JPMI", name: "Jpm Insufficient Corp" }],
} as unknown as ScoresPayload;

describe("crossSearch", () => {
  it("finds a company in a table that is not on screen", () => {
    const hits = crossSearch(scores, "jpmorgan", "operating");
    expect(hits.map((h) => [h.ticker, h.table])).toEqual([["JPM", "financials"]]);
  });

  it("leaves out the table on screen, which already filters itself", () => {
    const hits = crossSearch(scores, "jpm", "financials");
    expect(hits.map((h) => h.ticker)).not.toContain("JPM");
  });

  it("finds an unranked company, and stops listing them once that table is open", () => {
    expect(crossSearch(scores, "jpmi", "operating").map((h) => h.table)).toEqual(["insufficient"]);
    expect(crossSearch(scores, "jpmi", "insufficient")).toEqual([]);
  });

  it("puts an exact ticker first, then tickers that start with the text", () => {
    const hits = crossSearch(scores, "jpm", "reits");
    expect(hits[0].ticker).toBe("JPM");
    expect(hits.map((h) => h.ticker)).toEqual(["JPM", "JPMI", "JPMX"]);
  });

  it("returns nothing for an empty search", () => {
    expect(crossSearch(scores, "  ", "operating")).toEqual([]);
  });
});
