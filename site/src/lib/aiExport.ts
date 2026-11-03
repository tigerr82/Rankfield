import { metricValue } from "./format";
import type { FactorKey, HistoryIndex, MetricSpec, ScoresPayload, SegmentKey, StockRow } from "../data/types";

/** How many rows of a table go into one paste. The default is short; a whole table is long for some chats. */
export const TABLE_ROWS = 100;
export const ROW_CHOICES: number[] = [100, 250, 500];

const FACTOR_ORDER: FactorKey[] = ["quality", "growth", "valuation", "health"];
const FACTOR_SHORT: Record<FactorKey, string> = { quality: "Q", growth: "G", valuation: "V", health: "H" };

const METHOD_URL = "https://tigerr82.github.io/Rankfield/#/methodology";

function intro(month: string, weightsVersion: string): string {
  return [
    `Rankfield - sector-relative equity scores, month ${month} (methodology ${weightsVersion}).`,
    "Scores are percentiles (0-100) within a company's own sector or peer group, so they are",
    "relative, not absolute. Four equal factors: Quality (Q), Growth (G), Value (V), Health (H);",
    "the composite is their average. Rank 1 is best within its table. Rank change is positive when",
    "the company moved up since last month. Not investment advice.",
  ].join("\n");
}

const num = (value: number | null | undefined, digits = 1) =>
  value == null ? "-" : value.toFixed(digits);

const change = (value: number | null) => (value == null ? "-" : value > 0 ? `+${value}` : `${value}`);

/** Plain text for the open table: its best `limit` companies by rank, or all of them when `limit` is null. */
export function tablePrompt(scores: ScoresPayload, segment: SegmentKey, limit: number | null = TABLE_ROWS): string {
  const meta = scores.meta;
  const label = scores.segments_meta.find((s) => s.key === segment)?.label ?? segment;
  const all = [...(scores.segments[segment] ?? [])].sort((a, b) => a.rank - b.rank);
  const rows = limit == null ? all : all.slice(0, limit);
  const lines = rows.map((r) =>
    [
      r.rank,
      r.ticker,
      r.name,
      r.peer_group ?? r.sector ?? "-",
      num(r.composite),
      ...FACTOR_ORDER.map((k) => num(r.factors[k], 0)),
      change(r.rank_change),
      r.price_change_pct == null ? "-" : `${r.price_change_pct.toFixed(1)}%`,
    ].join(" | "),
  );
  return [
    intro(meta.scoring_date, meta.weights_version),
    "",
    `Table: ${label}. ${rows.length === all.length ? `All ${all.length} companies` : `The top ${rows.length} of ${all.length} companies by rank`}.`,
    "Columns: rank | ticker | name | sector or peer group | composite | Q | G | V | H | rank change | 1-month price change",
    ...lines,
    "",
    `Method: ${METHOD_URL}`,
  ].join("\n");
}

/** Plain text for one company, with every metric behind its factors. */
export function companyPrompt(scores: ScoresPayload, row: StockRow): string {
  const meta = scores.meta;
  const table = scores.segments_meta.find((s) => s.key === row.segment)?.label ?? row.segment;
  const size = scores.segments[row.segment]?.length ?? 0;
  const specs = new Map<string, MetricSpec>(scores.metrics.map((m) => [m.key, m]));
  const factorLines = FACTOR_ORDER.map((key) => {
    const name = scores.factors.find((f) => f.key === key)?.label ?? key;
    const metrics = Object.entries(row.metrics)
      .filter(([k]) => specs.get(k)?.factor === key)
      .map(([k, cell]) => {
        const spec = specs.get(k)!;
        const raw = metricValue(cell.raw, spec);
        return `    ${spec.label}: ${raw} (percentile ${num(cell.pct, 0)})`;
      });
    return [`${name} ${FACTOR_SHORT[key]}: ${num(row.factors[key], 0)}`, ...metrics].join("\n");
  });
  return [
    intro(meta.scoring_date, meta.weights_version),
    "",
    `${row.ticker} - ${row.name}`,
    `Table: ${table} (${size} companies). Group: ${row.peer_group ?? row.sector ?? "-"}.`,
    `Composite ${num(row.composite)}, rank ${row.rank} of ${size}, rank change since last month ${change(row.rank_change)}.`,
    `Price ${row.price}, 1-month change ${row.price_change_pct == null ? "-" : row.price_change_pct.toFixed(1) + "%"}.`,
    `Fundamentals as of ${row.fundamentals_asof ?? "-"} (${row.form ?? "-"} filed ${row.filed ?? "-"}).`,
    "",
    ...factorLines,
    "",
    `Method: ${METHOD_URL}`,
  ].join("\n");
}

export const DATA_PACK_FILE = "rankfield_data_pack.zip";

export function packUrl(): string {
  return `${import.meta.env.BASE_URL.replace(/\/+$/, "")}/data/${DATA_PACK_FILE}`;
}

/** Rough size of a pasted text, in thousands of tokens. */
export const approxTokensK = (text: string) => Math.max(1, Math.round(text.length / 3.5 / 1000));

export interface Selection {
  tickers: string[];
  /** Latest n months, or null for every month on record. */
  months: number | null;
  /**
   * "scores": rank, composite and the four factors per month. "latest": adds every metric of the latest month.
   * "full": adds every metric of every month asked for, read from the data pack.
   */
  depth: "scores" | "latest" | "full";
}

/**
 * A few companies over time, as pasted text. The history carries rank, composite, factors and price for every
 * month; the metrics behind them are held for the latest month only, so older months' metrics are in the data
 * pack, not here.
 */
export function selectionPrompt(
  scores: ScoresPayload,
  history: HistoryIndex | undefined,
  sel: Selection,
  packMetrics?: Map<string, string[]>,
): string {
  const rows = new Map<string, StockRow>();
  for (const list of Object.values(scores.segments) as StockRow[][]) for (const r of list) rows.set(r.ticker, r);
  const out: string[] = [intro(scores.meta.scoring_date, scores.meta.weights_version), ""];
  const unknown: string[] = [];
  for (const raw of sel.tickers) {
    const ticker = raw.trim().toUpperCase();
    const row = rows.get(ticker);
    const points = history?.tickers[ticker] ?? [];
    if (!row && !points.length) {
      unknown.push(ticker);
      continue;
    }
    const shown = sel.months == null ? points : points.slice(-sel.months);
    out.push(`${ticker} - ${row?.name ?? ""} (${row?.peer_group ?? row?.sector ?? "-"})`);
    out.push("month | rank | composite | Q | G | V | H | price | method version");
    for (const p of shown) {
      out.push(
        [
          p.month, p.rank ?? "-", num(p.composite),
          ...FACTOR_ORDER.map((k) => num(p.factors?.[k] ?? null, 0)),
          p.price ?? "-", p.weights_version + (p.backtested ? " (backtested)" : ""),
        ].join(" | "),
      );
    }
    if (sel.depth === "full") {
      const lines = packMetrics?.get(ticker) ?? [];
      out.push(lines.length ? "Every metric, by month (value, then sector percentile):" : "No metrics on record for this company in these months.");
      out.push(...lines);
    }
    if (sel.depth === "latest" && row) {
      out.push(`Metrics behind the latest month (${scores.meta.scoring_date}):`);
      for (const [key, cell] of Object.entries(row.metrics)) {
        const spec = scores.metrics.find((m) => m.key === key);
        if (spec) out.push(`  ${spec.label} [${spec.factor}]: ${metricValue(cell.raw, spec)} (percentile ${num(cell.pct, 0)})`);
      }
    }
    out.push("");
  }
  if (unknown.length) out.push(`Not found in the ranked tables: ${unknown.join(", ")}`, "");
  out.push("A month in which a company was not ranked is missing from its list. August and September 2026 were rebuilt after the fact on the current method.");
  out.push(`Method: ${METHOD_URL}`);
  return out.join("\n");
}

/**
 * Every metric of the chosen companies and months, from the data pack's metrics file, grouped by metric so a
 * trend reads along one line: `ROIC [quality]: 2026-08 22.7% (p86) | 2026-09 ...`.
 */
export function packMetricLines(
  csv: string,
  scores: ScoresPayload,
  tickers: string[],
  months: string[] | null,
): Map<string, string[]> {
  const wanted = new Set(tickers.map((t) => t.toUpperCase()));
  const monthSet = months ? new Set(months) : null;
  const specs = new Map(scores.metrics.map((m) => [m.key, m]));
  const grouped = new Map<string, Map<string, string[]>>();
  const rows = csv.split(/\r?\n/);
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row) continue;
    const [month, ticker, metric, , raw, pct] = row.split(",");
    if (!wanted.has(ticker) || (monthSet && !monthSet.has(month))) continue;
    const spec = specs.get(metric);
    const value = raw === "" || raw == null ? "-" : spec ? metricValue(Number(raw), spec) : raw;
    const entry = `${month} ${value} (p${pct === "" || pct == null ? "-" : Math.round(Number(pct))})`;
    const byMetric = grouped.get(ticker) ?? new Map<string, string[]>();
    byMetric.set(metric, [...(byMetric.get(metric) ?? []), entry]);
    grouped.set(ticker, byMetric);
  }
  const out = new Map<string, string[]>();
  for (const [ticker, byMetric] of grouped) {
    out.set(
      ticker,
      [...byMetric.entries()].map(([metric, entries]) => {
        const spec = specs.get(metric);
        return `  ${spec?.label ?? metric}${spec ? ` [${spec.factor}]` : ""}: ${entries.join(" | ")}`;
      }),
    );
  }
  return out;
}
