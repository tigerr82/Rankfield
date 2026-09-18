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

const SORTS: { key: string; dir: 1 | -1; label: string; title: string }[] = [
  { key: "composite", dir: -1, label: "By score", title: "Highest Rankfield Score first" },
  { key: "price_change_pct", dir: -1, label: "Top gainers", title: "Biggest price gains since the prior scoring date" },
  { key: "price_change_pct", dir: 1, label: "Top decliners", title: "Biggest price declines since the prior scoring date" },
  { key: "rank_change", dir: -1, label: "Rank risers", title: "Largest improvements in rank versus last month" },
];

/**
 * Two rows that read as one sentence: which SEGMENT, how much of it to SHOW,
 * then how to SORT it. The scope switch sits next to the segments and names
 * the selected one ("All operating · 1,186"), because "All stocks" beside a
 * segment tab read as all 1,381 scored stocks when it meant one segment's.
 * Basic/Pro is not a filter - it changes the whole page - so it lives in the
 * app header (AppHeader), not here.
 */
export function Toolbar({ segmentsMeta, counts, shown, total, scopeCounts }: Props) {
  const { query, setQuery, sortKey, sortDir, setSort, segment, setSegment,
          scope, setScope, railCollapsed, toggleRail } = useApp();
  const ref = useRef<HTMLDivElement | null>(null);
  useToolbarHeight(ref);

  const ranked = segment !== "insufficient";
  const noun = segmentNoun(segment);
  const scoredTotal = segmentsMeta.reduce((sum, meta) => sum + (counts[meta.key] ?? 0), 0);

  return (
    <div className="toolbar" ref={ref}>
      <div className="tbrow">
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

        <span className="tbgroup">
          <span className="tblabel">Segment</span>
          <div className="seg segtabs" role="group" aria-label="Segment">
            {segmentsMeta.map((meta) => (
              <button
                key={meta.key}
                type="button"
                className={segment === meta.key ? "on" : ""}
                aria-pressed={segment === meta.key}
                onClick={() => setSegment(meta.key as SegmentKey)}
                title={`${meta.label} — ranked separately, never against the other segments`}
              >
                {shortLabel(meta.label)} <span className="mono">{(counts[meta.key] ?? 0).toLocaleString()}</span>
              </button>
            ))}
            {/* In the same group, so the four read as one choice; set apart only
                by a dashed divider and quieter text, because it lists what could
                not be ranked rather than ranking anything. */}
            <button
              type="button"
              className={`aside${segment === "insufficient" ? " on" : ""}`}
              aria-pressed={segment === "insufficient"}
              onClick={() => setSegment("insufficient")}
              title="Stocks that resolved too few metrics to rank — unranked, not low-ranked"
            >
              Insufficient data <span className="mono">{(counts.insufficient ?? 0).toLocaleString()}</span>
            </button>
          </div>
        </span>

        {ranked && scopeCounts && (
          <span className="tbgroup">
            <span className="tblabel">Show</span>
            {/* Both scopes stay visible. A single button that showed only the
                current mode made the other one something you had to guess at. */}
            <div className="seg" role="group" aria-label={`How much of the ${noun} table to show`}>
              <button
                type="button"
                className={scope === "top_decile" ? "on" : ""}
                aria-pressed={scope === "top_decile"}
                onClick={() => setScope("top_decile")}
                title="The best 10% of each sector in this table. A global top list would be dominated by whichever sectors score high on absolute numbers."
              >
                Top 10% per sector <span className="mono">· {scopeCounts.top.toLocaleString()}</span>
              </button>
              <button
                type="button"
                className={scope === "all" ? "on" : ""}
                aria-pressed={scope === "all"}
                onClick={() => setScope("all")}
                title={`Every scored stock in the ${noun} table.`}
              >
                All {noun} <span className="mono">· {scopeCounts.all.toLocaleString()}</span>
              </button>
            </div>
          </span>
        )}

        <span className="count">
          {ranked ? (
            <>
              {shown.toLocaleString()} of {total.toLocaleString()} {noun}
              <span className="countsub"> · {scoredTotal.toLocaleString()} scored across {segmentsMeta.length} segments</span>
            </>
          ) : (
            <>{shown.toLocaleString()} unranked · too few metrics resolved</>
          )}
        </span>
      </div>

      <div className="tbrow">
        {ranked && (
          <span className="tbgroup">
            <span className="tblabel">Sort</span>
            <div className="seg" role="group" aria-label="Sort order">
              {SORTS.map((s) => (
                <button
                  key={`${s.key}${s.dir}`}
                  type="button"
                  title={s.title}
                  className={sortKey === s.key && sortDir === s.dir ? "on" : ""}
                  aria-pressed={sortKey === s.key && sortDir === s.dir}
                  onClick={() => setSort(s.key, s.dir)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </span>
        )}

        <input
          type="search"
          className="search"
          placeholder="Search ticker or company…"
          autoComplete="off"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search by ticker or company name"
        />
      </div>
    </div>
  );
}

function shortLabel(label: string): string {
  if (label.startsWith("Operating")) return "Operating";
  if (label.startsWith("Financials")) return "Financials";
  if (label.startsWith("Pre-revenue")) return "Pre-revenue";
  return label;
}

/** The selected table, as the noun the scope switch and the counter use. */
export function segmentNoun(segment: string): string {
  if (segment === "operating") return "operating";
  if (segment === "financials") return "financials";
  if (segment === "pre_revenue") return "pre-revenue";
  return "stocks";
}
