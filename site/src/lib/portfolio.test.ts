import { beforeEach, describe, expect, it } from "vitest";

/**
 * The watchlist is a timestamped event log, not a flat list, for one reason:
 * applying today's holdings to a past period would credit gains that were never
 * captured. These tests defend that property directly.
 */

// Minimal in-memory localStorage; the module reads it at call time, not import.
class MemoryStorage {
  private store = new Map<string, string>();
  getItem(k: string) { return this.store.has(k) ? this.store.get(k)! : null; }
  setItem(k: string, v: string) { this.store.set(k, v); }
  removeItem(k: string) { this.store.delete(k); }
  clear() { this.store.clear(); }
}

const storage = new MemoryStorage();
(globalThis as unknown as { localStorage: MemoryStorage }).localStorage = storage;

const {
  allEvents, currentHoldings, encodeSharedHoldings, heldOn, holdingsOn, importSharedHoldings,
  isHeld, logStart, parseSharedHoldings, removeAll, toggle,
} = await import("./portfolio");
type WatchEvent = Awaited<ReturnType<typeof toggle>>[number];

beforeEach(() => storage.clear());

describe("toggle", () => {
  it("adds a position with an added_at and no removed_at", () => {
    toggle("AAPL");
    const [event] = allEvents();
    expect(event.ticker).toBe("AAPL");
    expect(event.added_at).toBeTruthy();
    expect(event.removed_at).toBeNull();
    expect(isHeld("AAPL")).toBe(true);
  });

  it("closes the open event rather than deleting it", () => {
    toggle("AAPL");
    toggle("AAPL");
    const events = allEvents();
    expect(events).toHaveLength(1);          // history retained
    expect(events[0].removed_at).toBeTruthy();
    expect(isHeld("AAPL")).toBe(false);
  });

  it("re-adding opens a second event, preserving the first", () => {
    toggle("AAPL");
    toggle("AAPL");
    toggle("AAPL");
    const events = allEvents();
    expect(events).toHaveLength(2);
    expect(events[0].removed_at).toBeTruthy();
    expect(events[1].removed_at).toBeNull();
    expect(currentHoldings()).toEqual(["AAPL"]);
  });
});

describe("removeAll", () => {
  it("records removals instead of erasing history", () => {
    toggle("AAPL");
    toggle("MSFT");
    removeAll();
    expect(currentHoldings()).toEqual([]);
    expect(allEvents()).toHaveLength(2);
    expect(allEvents().every((e) => e.removed_at)).toBe(true);
  });
});

describe("heldOn - the hindsight guard", () => {
  const events = [
    { ticker: "OLD", added_at: "2026-01-10T00:00:00Z", removed_at: "2026-05-10T00:00:00Z" },
    { ticker: "NOW", added_at: "2026-09-01T00:00:00Z", removed_at: null },
  ];

  it("a position added today was NOT held at a past date", () => {
    // This is the property that stops a starred-today stock from retroactively
    // improving last month's reported return.
    expect(heldOn("NOW", "2026-07-31T00:00:00Z", events)).toBe(false);
  });

  it("a position held at the time counts", () => {
    expect(heldOn("OLD", "2026-03-01T00:00:00Z", events)).toBe(true);
  });

  it("a position sold before the date does not count", () => {
    expect(heldOn("OLD", "2026-07-31T00:00:00Z", events)).toBe(false);
  });

  it("the removal boundary is exclusive and the add boundary inclusive", () => {
    expect(heldOn("OLD", "2026-01-10T00:00:00Z", events)).toBe(true);
    expect(heldOn("OLD", "2026-05-10T00:00:00Z", events)).toBe(false);
  });

  it("an unknown ticker is never held", () => {
    expect(heldOn("NOPE", "2026-03-01T00:00:00Z", events)).toBe(false);
  });

  it("holdingsOn returns only what was actually held then", () => {
    expect(holdingsOn("2026-03-01T00:00:00Z", events)).toEqual(["OLD"]);
    expect(holdingsOn("2026-09-30T00:00:00Z", events)).toEqual(["NOW"]);
  });
});

describe("logStart", () => {
  it("is null with no history, so the UI can show a dash rather than assume", () => {
    expect(logStart([])).toBeNull();
  });

  it("reports the earliest add", () => {
    expect(logStart([
      { ticker: "B", added_at: "2026-05-01T00:00:00Z", removed_at: null },
      { ticker: "A", added_at: "2026-01-01T00:00:00Z", removed_at: null },
    ])).toBe("2026-01-01T00:00:00Z");
  });
});

describe("resilience", () => {
  it("survives corrupt stored data rather than throwing", () => {
    storage.setItem("rankfield_watchlist_v1", "{not json");
    expect(allEvents()).toEqual([]);
    expect(currentHoldings()).toEqual([]);
  });

  it("discards malformed entries", () => {
    storage.setItem("rankfield_watchlist_v1", JSON.stringify([{ nope: 1 }, { ticker: "OK", added_at: "2026-01-01", removed_at: null }]));
    expect(allEvents()).toHaveLength(1);
    expect(allEvents()[0].ticker).toBe("OK");
  });

  it("treats a non-array payload as empty", () => {
    storage.setItem("rankfield_watchlist_v1", JSON.stringify({ ticker: "X" }));
    expect(allEvents()).toEqual([]);
  });
});

describe("sharing the portfolio in a link", () => {
  it("encodes the open positions with the day each was opened", () => {
    const events: WatchEvent[] = [
      { ticker: "MU", added_at: "2026-09-01T10:00:00.000Z", removed_at: null },
      { ticker: "GOOGL", added_at: "2026-09-15T08:30:00.000Z", removed_at: null },
      { ticker: "SOLD", added_at: "2026-08-01T08:30:00.000Z", removed_at: "2026-09-20T09:00:00.000Z" },
    ];
    expect(encodeSharedHoldings(events)).toBe("MU:2026-09-01,GOOGL:2026-09-15");
  });

  it("round-trips", () => {
    const events: WatchEvent[] = [{ ticker: "AAPL", added_at: "2026-07-04T00:00:00.000Z", removed_at: null }];
    expect(parseSharedHoldings(encodeSharedHoldings(events))).toEqual([
      { ticker: "AAPL", added_at: "2026-07-04" },
    ]);
  });

  it("drops anything malformed rather than guessing", () => {
    const parsed = parseSharedHoldings("MU:2026-09-01,,<script>:2026-09-01,MU:2026-01-01,TOOLONGTICKER:x");
    expect(parsed.map((p) => p.ticker)).toEqual(["MU"]);
  });

  it("an empty or absent parameter shares nothing", () => {
    expect(parseSharedHoldings(null)).toEqual([]);
    expect(parseSharedHoldings("")).toEqual([]);
  });

  it("a portfolio someone sent starts today, so the record is not backdated", () => {
    importSharedHoldings([{ ticker: "MU", added_at: "2020-01-01" }], false);
    const [event] = allEvents();
    expect(event.ticker).toBe("MU");
    expect(new Date(event.added_at).getFullYear()).toBe(new Date().getFullYear());
  });

  it("your own portfolio on a second device keeps its start dates", () => {
    importSharedHoldings([{ ticker: "GOOGL", added_at: "2026-07-04" }], true);
    const event = allEvents().find((e) => e.ticker === "GOOGL");
    expect(event?.added_at.slice(0, 10)).toBe("2026-07-04");
  });

  it("does not duplicate a position already held", () => {
    importSharedHoldings([{ ticker: "NVDA", added_at: "2026-07-04" }], true);
    importSharedHoldings([{ ticker: "NVDA", added_at: "2026-01-01" }], true);
    expect(allEvents().filter((e) => e.ticker === "NVDA")).toHaveLength(1);
  });
});
