import type { ReactNode } from "react";
import type { HistoryPoint } from "../data/types";
import type { RankedRow } from "../lib/scoring";
import { DASH, dayMonth, fullDate, marketCap, money, monthShort } from "../lib/format";
import { DeltaCell, ScoreCell, Sparkline, StabilityCell, StarButton } from "./cells";

export interface ColumnContext {
  isHeld: (ticker: string) => boolean;
  toggleHolding: (ticker: string) => void;
  history: Record<string, HistoryPoint[]>;
  totalRows: number;
  /** Tag each ticker with its segment - set by the portfolio when it holds
   *  stocks from more than one, since each is ranked within its own. */
  showSegment?: boolean;
}

const SEGMENT_TAGS: Record<string, [string, string]> = {
  operating: ["OPR", "Ranked within Operating companies"],
  financials: ["FIN", "Ranked within Banks, insurers & asset managers"],
  reits: ["REI", "Ranked within REITs & property"],
  pre_revenue: ["PRE", "Ranked within Pre-revenue / biotech"],
};

/** The price dates behind the rows on screen, for labelling column headers. */
export interface HeaderDates {
  price: string | null;
  prior: string | null;
}

export interface Column {
  key: string;
  header: string;
  /** A second, smaller header line - used to put the date on the price columns. */
  subheader?: (dates: HeaderDates) => string | null;
  /** Full name for the column-visibility control and the header tooltip. */
  title: string;
  align: "l" | "r" | "c";
  width: number;
  /** Pro-only columns are hidden in Basic mode. */
  pro?: boolean;
  sticky?: boolean;
  nosort?: boolean;
  cls?: string;
  /** Columns the user may not hide - without these a row is unidentifiable. */
  locked?: boolean;
  sortValue?: (row: RankedRow) => number | string | null;
  render: (row: RankedRow, ctx: ColumnContext) => ReactNode;
}

/**
 * Column widths are budgeted, not content-driven: at 16 columns the table must
 * still fit a laptop without horizontal scrolling, so headers are short, cells
 * are tight, and long text truncates with an ellipsis. Horizontal scroll is a
 * fallback for narrow windows, never the normal state.
 */
export const COLUMNS: Column[] = [
  {
    key: "_star",
    header: "★",
    title: "My Portfolio",
    align: "c",
    width: 26,
    nosort: true,
    locked: true,
    render: (row, ctx) => (
      <StarButton on={ctx.isHeld(row.ticker)} onClick={() => ctx.toggleHolding(row.ticker)} />
    ),
  },
  {
    key: "_rank",
    header: "#",
    title:
      "Rank within the whole table, not a position in the list on screen. The top-decile view "
      + "takes the best tenth of each sector, so a strong company in a weak sector can carry a "
      + "high number here.",
    align: "r",
    width: 34,
    cls: "rk",
    locked: true,
    sortValue: (row) => row.liveRank,
    render: (row) => row.liveRank,
  },
  {
    key: "ticker",
    header: "Ticker",
    title: "Ticker",
    align: "l",
    width: 76,
    sticky: true,
    cls: "stick",
    locked: true,
    sortValue: (row) => row.ticker,
    render: (row, ctx) => (
      <>
        <span className="tk">{row.ticker}</span>
        {ctx.showSegment && SEGMENT_TAGS[row.segment] ? (
          <span className="exch segtag" title={SEGMENT_TAGS[row.segment][1]}>
            {SEGMENT_TAGS[row.segment][0]}
          </span>
        ) : (
          <span className="exch">{row.exchange}</span>
        )}
      </>
    ),
  },
  {
    key: "name",
    header: "Company",
    title: "Company name",
    align: "l",
    width: 150,
    cls: "nm",
    sortValue: (row) => row.name,
    render: (row) => <span title={row.name}>{cleanName(row.name)}</span>,
  },
  {
    key: "sector",
    header: "Sector",
    title: "Sector",
    align: "l",
    width: 94,
    cls: "sec",
    sortValue: (row) => row.sector ?? "",
    render: (row) => <span title={row.sector ?? ""}>{shortSector(row.sector)}</span>,
  },
  {
    key: "market_cap",
    header: "Cap",
    title: "Market capitalisation",
    align: "r",
    width: 58,
    cls: "mono",
    sortValue: (row) => row.market_cap,
    render: (row) => marketCap(row.market_cap),
  },
  {
    key: "price",
    header: "Price",
    // Prices are the close on the scoring date and move forward only at the next
    // monthly run, so the date sits on the column itself rather than being left
    // for the reader to assume "today".
    title: "Closing price on the scoring date. Prices update once a month, at each scoring run - not daily.",
    subheader: (d) => (d.price ? dayMonth(d.price) : null),
    align: "r",
    width: 62,
    cls: "mono",
    sortValue: (row) => row.price,
    render: (row) => (
      <span title={`Close on ${fullDate(row.price_at_scoring_asof)} · updates at the next monthly run`}>
        {money(row.price)}
      </span>
    ),
  },
  {
    key: "price_change_pct",
    header: "1-Mo %",
    title: "Price change from the previous scoring date to this one",
    subheader: (d) => (d.price && d.prior ? `${monthShort(d.prior)}→${monthShort(d.price)}` : null),
    align: "r",
    width: 66,
    sortValue: (row) => row.price_change_pct,
    render: (row) => (
      <DeltaCell
        value={row.price_change_pct}
        suffix="%"
        title={
          row.prior_price_date
            ? `${money(row.prior_price)} on ${fullDate(row.prior_price_date)} → ${money(row.price)} on ${fullDate(row.price_at_scoring_asof)}`
            : "No prior scoring date yet - this is the first run for this stock"
        }
      />
    ),
  },
  {
    key: "rank_change",
    header: "Δ Rank",
    title: "Rank change versus last month",
    align: "r",
    width: 50,
    pro: true,
    sortValue: (row) => row.rank_change,
    render: (row) => <DeltaCell value={row.rank_change} digits={0} />,
  },
  {
    key: "_spark",
    header: "Trend",
    title: "Composite over the trailing 12 months",
    align: "l",
    width: 44,
    pro: true,
    nosort: true,
    render: (row, ctx) => <Sparkline points={ctx.history[row.ticker] ?? []} />,
  },
  {
    key: "_stability",
    header: "Stable",
    title: "Rank range across plausible weightings",
    align: "l",
    width: 56,
    pro: true,
    sortValue: (row) => row.stability?.score ?? null,
    render: (row, ctx) => <StabilityCell stability={row.stability} total={ctx.totalRows} />,
  },
  {
    key: "quality",
    header: "Qual",
    title: "Quality factor score",
    align: "r",
    width: 48,
    pro: true,
    sortValue: (row) => row.factors.quality,
    render: (row) => <ScoreCell value={row.factors.quality} />,
  },
  {
    key: "growth",
    header: "Grow",
    title: "Growth factor score (ROIC-conditioned)",
    align: "r",
    width: 48,
    pro: true,
    sortValue: (row) => row.factors.growth,
    render: (row) => <ScoreCell value={row.factors.growth} />,
  },
  {
    key: "valuation",
    header: "Value",
    title: "Value factor score",
    align: "r",
    width: 48,
    pro: true,
    sortValue: (row) => row.factors.valuation,
    render: (row) => <ScoreCell value={row.factors.valuation} />,
  },
  {
    key: "health",
    header: "Hlth",
    title: "Financial Health factor score",
    align: "r",
    width: 48,
    pro: true,
    sortValue: (row) => row.factors.health,
    render: (row) => <ScoreCell value={row.factors.health} />,
  },
  {
    key: "composite",
    header: "Score",
    title: "Rankfield Score",
    align: "r",
    width: 56,
    locked: true,
    sortValue: (row) => row.liveComposite,
    render: (row) => <ScoreCell value={row.liveComposite} variant="comp" />,
  },
];

/** Nasdaq's sector names are too long for any column width that also leaves room
 *  for the rest of the table, so they truncated to something unreadable
 *  ("Consumer Di…"). These short forms fit in full; the unabbreviated name stays
 *  in the cell's tooltip and everywhere outside the table. */
const SECTOR_SHORT: Record<string, string> = {
  "Consumer Discretionary": "Cons. Disc.",
  "Consumer Staples": "Cons. Staples",
  "Basic Materials": "Materials",
  "Telecommunications": "Telecom",
  "Health Care": "Health Care",
  "Miscellaneous": "Misc.",
  "Real Estate": "Real Estate",
};

export function shortSector(sector: string | null): string {
  if (!sector) return DASH;
  return SECTOR_SHORT[sector] ?? sector;
}

/** Nasdaq appends the security type to every name; the table only needs the
 *  company. */
export function cleanName(name: string): string {
  return name
    .replace(/\s+Common Stock.*$/i, "")
    .replace(/\s+Ordinary Shares.*$/i, "")
    .replace(/\s+Class ([A-Z])\s*$/i, " ($1)")
    .trim();
}

export function activeColumns(mode: "basic" | "pro", hidden: string[]): Column[] {
  return COLUMNS.filter((c) => (mode === "pro" || !c.pro) && (c.locked || !hidden.includes(c.key)));
}
