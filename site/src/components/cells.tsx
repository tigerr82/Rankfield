import type { HistoryPoint, Stability } from "../data/types";
import { DASH } from "../lib/format";

/**
 * Score cell: magnitude is encoded as a recessive horizontal fill behind the
 * number so a column can be scanned without reading every digit. The number
 * stays the primary element - the bar never competes with it.
 */
export function ScoreCell({ value, variant }: { value: number | null; variant?: "comp" }) {
  if (value == null) {
    return (
      <span className={`sc na ${variant ?? ""}`} title="Not scored - the metric was not reported">
        {DASH}
      </span>
    );
  }
  return (
    <span className={`sc ${variant ?? ""}`}>
      <span className="fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      <span className="n">{value.toFixed(1)}</span>
    </span>
  );
}

/**
 * Change cell. Never encoded by colour alone: every value carries a sign and a
 * directional arrow, so it stays readable in greyscale, in print, and for
 * colourblind readers.
 */
export function DeltaCell({
  value,
  suffix = "",
  digits = 2,
  title,
}: {
  value: number | null;
  suffix?: string;
  digits?: number;
  title?: string;
}) {
  if (value == null) {
    return (
      <span className="delta flat" title={title ?? "No prior scoring date to compare against"}>
        {DASH}
      </span>
    );
  }
  const cls = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const arrow = value > 0 ? "▲" : value < 0 ? "▼" : "·";
  return (
    <span className={`delta ${cls}`} title={title}>
      <span className="ar" aria-hidden="true">
        {arrow}
      </span>
      {value > 0 ? "+" : ""}
      {value.toFixed(digits)}
      {suffix}
    </span>
  );
}

/** Composite over the trailing months. Renders an honest empty state during the
 *  warm-up period rather than a flat line implying stability that has not been
 *  observed. */
export function Sparkline({ points, width = 54, height = 16 }: { points: HistoryPoint[]; width?: number; height?: number }) {
  const values = points.map((p) => p.composite).filter((v): v is number => v != null);
  if (values.length < 2) {
    return (
      <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)" }} title="History begins accumulating from the first run; a sparkline needs at least two months.">
        accruing
      </span>
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const d = values
    .map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - ((v - min) / span) * height).toFixed(1)}`)
    .join(" ");
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-label={`Composite over ${values.length} months`}>
      <path d={d} fill="none" stroke={rising ? "var(--up)" : "var(--down)"} strokeWidth="1.3" />
    </svg>
  );
}

/**
 * Stability across methodology - how far the rank travels when the weights are
 * swept across plausible values. A stock in the top quintile under nearly any
 * sensible weighting is materially different from one that is top-quintile only
 * at the default.
 */
export function StabilityCell({ stability, total }: { stability: Stability | null; total: number }) {
  if (!stability) return <span className="delta flat">{DASH}</span>;
  const left = (stability.rank_min / Math.max(total, 1)) * 100;
  const width = Math.max(2, ((stability.rank_max - stability.rank_min) / Math.max(total, 1)) * 100);
  return (
    <span
      className="stab"
      title={`Ranks between ${stability.rank_min} and ${stability.rank_max} across ${stability.weightings_tested} plausible weightings`}
    >
      <span className="track">
        <span className="span" style={{ left: `${left}%`, width: `${width}%` }} />
      </span>
      {stability.rank_min}–{stability.rank_max}
    </span>
  );
}

export function StarButton({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      className={`star ${on ? "on" : ""}`}
      aria-pressed={on}
      aria-label={on ? "Remove from My Portfolio" : "Add to My Portfolio"}
      title={on ? "Remove from My Portfolio" : "Add to My Portfolio"}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      {on ? "★" : "☆"}
    </button>
  );
}
