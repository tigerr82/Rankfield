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
