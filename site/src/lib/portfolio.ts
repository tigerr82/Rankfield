/**
 * The watchlist, stored as a timestamped event log rather than a flat list.
 *
 * This is not over-engineering. A flat list of today's holdings, applied to past
 * periods, would credit the user with gains they never captured and produce a
 * flattering, meaningless track record. The log records when each position was
 * actually added and removed, so portfolio returns can be computed only over the
 * windows each stock was genuinely held.
 *
 * Retrofitting this later means the portfolio-versus-universe record can only
 * begin from the day it is fixed - which is why it ships in v1.
 */
const KEY = "rankfield_watchlist_v1";

export interface WatchEvent {
  ticker: string;
  added_at: string;   // ISO timestamp
  removed_at: string | null;
}

function read(): WatchEvent[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (e): e is WatchEvent => !!e && typeof e.ticker === "string" && typeof e.added_at === "string",
    );
  } catch {
    return [];
  }
}

function write(events: WatchEvent[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(events));
  } catch {
    /* private mode or blocked site data: the session still works, it just
       cannot remember the watchlist. */
  }
}

export function allEvents(): WatchEvent[] {
  return read();
}

export function currentHoldings(events: WatchEvent[] = read()): string[] {
  const open = events.filter((e) => e.removed_at == null).map((e) => e.ticker);
  return [...new Set(open)];
}

export function isHeld(ticker: string, events: WatchEvent[] = read()): boolean {
  return events.some((e) => e.ticker === ticker && e.removed_at == null);
}

export function toggle(ticker: string): WatchEvent[] {
  const events = read();
  const now = new Date().toISOString();
  const open = events.find((e) => e.ticker === ticker && e.removed_at == null);
  if (open) {
    open.removed_at = now;
  } else {
    events.push({ ticker, added_at: now, removed_at: null });
  }
  write(events);
  return events;
}

/** "Remove all" records removals; it never erases history. */
export function removeAll(): WatchEvent[] {
  const events = read();
  const now = new Date().toISOString();
  for (const e of events) if (e.removed_at == null) e.removed_at = now;
  write(events);
  return events;
}

/** Was this position actually held on this date? The whole point of the log. */
export function heldOn(ticker: string, when: string, events: WatchEvent[] = read()): boolean {
  const t = new Date(when).getTime();
  return events.some((e) => {
    if (e.ticker !== ticker) return false;
    const from = new Date(e.added_at).getTime();
    const to = e.removed_at ? new Date(e.removed_at).getTime() : Infinity;
    return from <= t && t < to;
  });
}

/** Which tickers were held at the start of a given scoring period. */
export function holdingsOn(when: string, events: WatchEvent[] = read()): string[] {
  return [...new Set(events.map((e) => e.ticker))].filter((t) => heldOn(t, when, events));
}

/** The earliest moment the log knows about. Periods before this have no
 *  membership information, and the UI must show "—" rather than assume. */
export function logStart(events: WatchEvent[] = read()): string | null {
  if (!events.length) return null;
  return events.reduce((min, e) => (e.added_at < min ? e.added_at : min), events[0].added_at);
}

// --------------------------------------------------------------- sharing
//
// The portfolio lives in this browser and nowhere else, which loses it on a new
// device and makes it impossible to show anyone. Encoding the holdings into the
// link solves both without an account, a server or a password to leak.
//
// The format is deliberately readable - `MU:2026-09-01,GOOGL:2026-09-15` - so
// anyone can see exactly what a link they were sent contains before opening it.

export interface SharedHolding {
  ticker: string;
  added_at: string;    // ISO date, day precision
}

const TICKER = /^[A-Z][A-Z0-9.-]{0,9}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Today's open positions, with the day each was opened. */
export function encodeSharedHoldings(events: WatchEvent[] = read()): string {
  const open = new Map<string, string>();
  for (const e of events) {
    if (e.removed_at != null) continue;
    const day = e.added_at.slice(0, 10);
    const known = open.get(e.ticker);
    if (!known || day < known) open.set(e.ticker, day);   // the earliest open position wins
  }
  return [...open].map(([ticker, day]) => `${ticker}:${day}`).join(",");
}

/** Parse a shared link's parameter. Anything malformed is dropped, never guessed. */
export function parseSharedHoldings(param: string | null): SharedHolding[] {
  if (!param) return [];
  const out: SharedHolding[] = [];
  const seen = new Set<string>();
  for (const part of param.split(",")) {
    const [rawTicker, rawDay] = part.split(":");
    const ticker = (rawTicker || "").trim().toUpperCase();
    if (!TICKER.test(ticker) || seen.has(ticker)) continue;
    const day = (rawDay || "").trim();
    seen.add(ticker);
    out.push({ ticker, added_at: DAY.test(day) ? day : new Date().toISOString().slice(0, 10) });
  }
  return out;
}

/**
 * Add shared positions to this browser's log.
 *
 * `keepDates` is the honesty switch. Opening your own portfolio on a second
 * device should keep the day you actually bought; importing a portfolio someone
 * sent you must not, because you did not hold it then and the measured record
 * would credit you with months you never had. The caller asks the user which
 * one this is - the log cannot tell.
 */
export function importSharedHoldings(shared: SharedHolding[], keepDates: boolean): WatchEvent[] {
  const events = read();
  const now = new Date().toISOString();
  for (const item of shared) {
    if (events.some((e) => e.ticker === item.ticker && e.removed_at == null)) continue;
    events.push({
      ticker: item.ticker,
      added_at: keepDates ? `${item.added_at}T00:00:00.000Z` : now,
      removed_at: null,
    });
  }
  write(events);
  return events;
}
