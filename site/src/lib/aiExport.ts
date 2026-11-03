import { metricValue } from "./format";
import type { FactorKey, MetricSpec, ScoresPayload, SegmentKey, StockRow } from "../data/types";

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
