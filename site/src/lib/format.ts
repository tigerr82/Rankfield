import type { MetricSpec } from "../data/types";

export const DASH = "—"; // em dash: what a missing value renders as, never 0

export function money(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function marketCap(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  return `$${value.toFixed(0)}`;
}

export function percent(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

/** Raw metric values, in the unit the metric is actually quoted in. */
export function metricValue(value: number | null | undefined, spec: MetricSpec): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  switch (spec.unit) {
    case "pct":
      return `${(value * 100).toFixed(1)}%`;
    case "pp":
      return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}pp`;
    case "x":
      return `${value.toFixed(2)}x`;
    default:
      return value.toFixed(2);
  }
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return iso;
}

export function monthLabel(month: string): string {
  const [y, m] = month.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(m) - 1] ?? m} ${y}`;
}

export function weeksSince(iso: string): number {
  const then = new Date(`${iso}T00:00:00Z`).getTime();
  return (Date.now() - then) / (1000 * 60 * 60 * 24 * 7);
}
