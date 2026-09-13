import { useEffect, useRef } from "react";
import type { SegmentKey, SegmentMeta } from "../data/types";
import { useApp } from "../state/AppState";

/**
 * The table header pins directly beneath the toolbar, so it needs the
 * toolbar's real height - which changes when the controls wrap on a narrow
 * window or when Pro mode adds buttons. Measuring it beats guessing: a stale
 * constant leaves the header floating over the first rows.
 */
function useToolbarHeight(ref: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const apply = () =>
      document.documentElement.style.setProperty("--toolbar-h", `${Math.round(el.getBoundingClientRect().height)}px`);
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
}

interface Props {
  segmentsMeta: SegmentMeta[];
  counts: Record<string, number>;
  shown: number;
  total: number;
  /** How many rows each scope would show under the current filters, so both
   *  options state their consequence before anyone clicks. */
  scopeCounts?: { top: number; all: number };
}

const MOVERS: { key: string; dir: 1 | -1; label: string; title: string }[] = [
  { key: "price_change_pct", dir: -1, label: "Top gainers", title: "Biggest price gains since the prior scoring date" },
  { key: "price_change_pct", dir: 1, label: "Top decliners", title: "Biggest price declines since the prior scoring date" },
  { key: "rank_change", dir: -1, label: "Rank risers", title: "Largest improvements in rank versus last month" },
  { key: "composite", dir: -1, label: "By score", title: "Highest Rankfield Score first" },
];

export function Toolbar({ segmentsMeta, counts, shown, total, scopeCounts }: Props) {
  const { mode, setMode, query, setQuery, sortKey, sortDir, setSort, segment, setSegment,
          scope, setScope, railCollapsed, toggleRail } = useApp();
  const ref = useRef<HTMLDivElement | null>(null);
  useToolbarHeight(ref);

  return (
    <div className="toolbar" ref={ref}>
      <button
        type="button"
        className="railtoggle"
        onClick={toggleRail}
        aria-pressed={!railCollapsed}
        aria-label={railCollapsed ? "Show the filter rail" : "Hide the filter rail"}
        title={railCollapsed
          ? "Show filters"
          : "Hide filters — gives the table the full window width"}
      >
        {railCollapsed ? "»" : "«"}
      </button>
      <div className="seg modeseg" role="group" aria-label="Detail level">
        <button type="button" className={mode === "basic" ? "on" : ""} onClick={() => setMode("basic")}>
          Basic
        </button>
        <button type="button" className={mode === "pro" ? "on" : ""} onClick={() => setMode("pro")}>
          Pro
        </button>
      </div>

      <input
        type="search"
        className="search"
        placeholder="Search ticker or company…"
        autoComplete="off"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Search by ticker or company name"
      />

      <div className="seg" role="group" aria-label="Universe segment">
        {segmentsMeta.map((meta) => (
          <button
            key={meta.key}
            type="button"
            className={segment === meta.key ? "on" : ""}
            onClick={() => setSegment(meta.key as SegmentKey)}
            title={`${meta.label} — ranked separately, never against each other`}
          >
            {shortLabel(meta.label)} <span className="mono">{counts[meta.key] ?? 0}</span>
          </button>
        ))}
        <button
          type="button"
          className={segment === "insufficient" ? "on" : ""}
          onClick={() => setSegment("insufficient")}
          title="Stocks that resolved too few metrics to rank — unranked, not low-ranked"
        >
          Insufficient <span className="mono">{counts.insufficient ?? 0}</span>
        </button>
      </div>

      {segment !== "insufficient" && (
        <>
          <span className="uppercase">Movers</span>
          {MOVERS.map((m) => (
            <button
              key={`${m.key}${m.dir}`}
              type="button"
              title={m.title}
              className={`pillbtn${sortKey === m.key && sortDir === m.dir ? " on" : ""}`}
              onClick={() => setSort(m.key, m.dir)}
            >
              {m.label}
            </button>
          ))}
          {/* Both scopes stay visible. A single button that showed only the
              current mode made the other one something you had to guess at. */}
          <span className="uppercase">Show</span>
          <div className="seg" role="group" aria-label="Which stocks to show">
            <button
              type="button"
              className={scope === "top_decile" ? "on" : ""}
              aria-pressed={scope === "top_decile"}
              onClick={() => setScope("top_decile")}
              title="The best 10% of each sector. A global top list would be dominated by whichever sectors score high on absolute numbers."
            >
              Top 10% per sector{scopeCounts && <span className="mono"> · {scopeCounts.top.toLocaleString()}</span>}
            </button>
            <button
              type="button"
              className={scope === "all" ? "on" : ""}
              aria-pressed={scope === "all"}
              onClick={() => setScope("all")}
              title="Every scored stock in this segment."
            >
              All stocks{scopeCounts && <span className="mono"> · {scopeCounts.all.toLocaleString()}</span>}
            </button>
          </div>
        </>
      )}

      <span className="count">
        {shown.toLocaleString()} of {total.toLocaleString()} stocks
      </span>
    </div>
  );
}

function shortLabel(label: string): string {
  if (label.startsWith("Operating")) return "Operating";
  if (label.startsWith("Financials")) return "Financials";
  if (label.startsWith("Pre-revenue")) return "Pre-revenue";
  return label;
}
