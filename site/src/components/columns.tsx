import type { ReactNode } from "react";
import type { HistoryPoint } from "../data/types";
import type { RankedRow } from "../lib/scoring";
import { DASH, marketCap, money } from "../lib/format";
import { DeltaCell, ScoreCell, Sparkline, StabilityCell, StarButton } from "./cells";

export interface ColumnContext {
  isHeld: (ticker: string) => boolean;
  toggleHolding: (ticker: string) => void;
  history: Record<string, HistoryPoint[]>;
  totalRows: number;
}

export interface Column {
  key: string;
  header: string;
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
    width: 32,
    nosort: true,
    locked: true,
    render: (row, ctx) => (
      <StarButton on={ctx.isHeld(row.ticker)} onClick={() => ctx.toggleHolding(row.ticker)} />
    ),
  },
  {
    key: "_rank",
    header: "#",
    title: "Rank",
    align: "r",
    width: 42,
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
    width: 84,
    sticky: true,
    cls: "stick",
    locked: true,
    sortValue: (row) => row.ticker,
    render: (row) => (
      <>
        <span className="tk">{row.ticker}</span>
        <span className="exch">{row.exchange}</span>
      </>
    ),
  },
  {
    key: "name",
    header: "Company",
    title: "Company name",
    align: "l",
    width: 168,
    cls: "nm",
    sortValue: (row) => row.name,
    render: (row) => <span title={row.name}>{cleanName(row.name)}</span>,
  },
  {
    key: "sector",
    header: "Sector",
    title: "Sector",
    align: "l",
    width: 102,
    cls: "sec",
    sortValue: (row) => row.sector ?? "",
    render: (row) => <span title={row.sector ?? ""}>{row.sector ?? DASH}</span>,
  },
  {
    key: "market_cap",
    header: "Cap",
    title: "Market capitalisation",
    align: "r",
    width: 68,
    cls: "mono",
    sortValue: (row) => row.market_cap,
    render: (row) => marketCap(row.market_cap),
  },
  {
    key: "price",
    header: "Price",
    title: "Adjusted close at the scoring date",
    align: "r",
    width: 72,
    cls: "mono",
    sortValue: (row) => row.price,
    render: (row) => money(row.price),
  },
  {
    key: "price_change_pct",
    header: "1-Mo %",
    title: "Price change since the prior scoring date",
    align: "r",
    width: 76,
    sortValue: (row) => row.price_change_pct,
    render: (row) => (
      <DeltaCell
        value={row.price_change_pct}
        suffix="%"
        title={
          row.prior_price_date
            ? `vs ${money(row.prior_price)} on ${row.prior_price_date}`
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
    width: 62,
    pro: true,
    sortValue: (row) => row.rank_change,
    render: (row) => <DeltaCell value={row.rank_change} digits={0} />,
  },
  {
    key: "_spark",
    header: "Trend",
    title: "Composite over the trailing 12 months",
    align: "l",
    width: 60,
    pro: true,
    nosort: true,
    render: (row, ctx) => <Sparkline points={ctx.history[row.ticker] ?? []} />,
  },
  {
    key: "_stability",
    header: "Stable",
    title: "Rank range across plausible weightings",
    align: "l",
    width: 64,
    pro: true,
    sortValue: (row) => row.stability?.score ?? null,
    render: (row, ctx) => <StabilityCell stability={row.stability} total={ctx.totalRows} />,
  },
  {
    key: "quality",
    header: "Quality",
    title: "Quality factor score",
    align: "r",
    width: 58,
    pro: true,
    sortValue: (row) => row.factors.quality,
    render: (row) => <ScoreCell value={row.factors.quality} />,
  },
  {
    key: "growth",
    header: "Growth",
    title: "Growth factor score (ROIC-conditioned)",
    align: "r",
    width: 58,
    pro: true,
    sortValue: (row) => row.factors.growth,
    render: (row) => <ScoreCell value={row.factors.growth} />,
  },
  {
    key: "valuation",
    header: "Value",
    title: "Value factor score",
    align: "r",
    width: 58,
    pro: true,
    sortValue: (row) => row.factors.valuation,
    render: (row) => <ScoreCell value={row.factors.valuation} />,
  },
  {
    key: "health",
    header: "Health",
    title: "Financial Health factor score",
    align: "r",
    width: 58,
    pro: true,
    sortValue: (row) => row.factors.health,
    render: (row) => <ScoreCell value={row.factors.health} />,
  },
  {
    key: "composite",
    header: "Score",
    title: "Rankfield Score",
    align: "r",
    width: 66,
    locked: true,
    sortValue: (row) => row.liveComposite,
    render: (row) => <ScoreCell value={row.liveComposite} variant="comp" />,
  },
];

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
