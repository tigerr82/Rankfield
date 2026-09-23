import { useMemo } from "react";
import type { InsufficientRow, ScoresPayload, SegmentKey, SegmentMeta, StockRow } from "../data/types";
import { usePayload } from "../data/usePayload";
import { Chips } from "../components/Chips";
import { FilterRail } from "../components/FilterRail";
import { PortfolioSection } from "../components/PortfolioSection";
import { SharedPortfolioBanner } from "../components/SharedPortfolio";
import { RankTable } from "../components/RankTable";
import { Shell, useScrollRef } from "../components/Shell";
import { Toolbar, segmentNoun } from "../components/Toolbar";
import { TableSkeleton } from "../components/Skeleton";
import { cleanName } from "../components/columns";
import { dayMonth, marketCap, monthShort, percent } from "../lib/format";
import { rankRows, type RankedRow } from "../lib/scoring";
import { CHG_ANY, useApp } from "../state/AppState";

export function RankingPage() {
  const { scores, history, loading, error } = usePayload();
  const scrollRef = useScrollRef();
  const app = useApp();

  const segmentRows: StockRow[] = useMemo(() => {
    if (!scores || app.segment === "insufficient") return [];
    return scores.segments[app.segment as SegmentKey] ?? [];
  }, [scores, app.segment]);

  // Re-ranked under the currently active weights. At the official weighting this
  // reproduces the stored ranks exactly.
  const official = scores?.meta.weights;
  const ranked = useMemo(
    () => rankRows(segmentRows, app.weights, official),
    [segmentRows, app.weights, official],
  );

  const sectorCounts = useMemo(() => {
    const counts = new Map<string, number>();
    const source = app.segment === "insufficient" ? scores?.insufficient ?? [] : segmentRows;
    for (const row of source) {
      const key = row.sector ?? "(unclassified)";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [segmentRows, scores, app.segment]);

  const { query, sectors, ranges, chgMin, sortKey, sortDir, scope } = app;
  const visible = useMemo(
    () => filterAndSort(ranked, app),
    // Depend on the individual filter values: `app` is a new object on every
    // render, so listing it alone defeated the memo entirely and re-sorted
    // 1,177 rows on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ranked, query, sectors, ranges, chgMin, sortKey, sortDir, scope],
  );

  // Row counts for both scopes under the current filters, shown on the scope
  // switch itself so each option says what it will do before it is clicked.
  const scopeCounts = useMemo(
    () => ({
      top: filterAndSort(ranked, { ...app, scope: "top_decile" }).length,
      all: filterAndSort(ranked, { ...app, scope: "all" }).length,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ranked, query, sectors, ranges, chgMin],
  );

  if (error) {
    return (
      <Shell scrollRef={scrollRef}>
        <div className="emptyq" style={{ padding: 60 }}>
          <strong>Could not load the score payload.</strong>
          {error}
        </div>
      </Shell>
    );
  }

  if (loading || !scores || !history) {
    return (
      <Shell scrollRef={scrollRef} rail={<aside className="rail" />}>
        <TableSkeleton />
      </Shell>
    );
  }

  return (
    <Shell
      scrollRef={scrollRef}
      rail={<FilterRail sectorCounts={sectorCounts} factors={scores.factors} />}
    >
      <Toolbar
        segmentsMeta={scores.segments_meta}
        counts={scores.meta.counts}
        shown={app.segment === "insufficient" ? scores.insufficient.length : visible.length}
        total={app.segment === "insufficient" ? scores.insufficient.length : ranked.length}
        scopeCounts={app.segment === "insufficient" ? undefined : scopeCounts}
      />
      <Chips factors={scores.factors} />
      <SharedPortfolioBanner />

      {/* Above every segment, Insufficient data included: the portfolio is the
          user's, so switching tabs or filtering the table never hides it. */}
      <PortfolioSection
        segments={scores.segments}
        metrics={scores.metrics}
        factors={scores.factors}
        history={history.tickers}
        scrollRef={scrollRef}
        official={scores.meta.weights}
        windowStart={scores.meta.prior_scoring_date}
        windowEnd={scores.meta.scoring_date}
      />

      {app.segment === "insufficient" ? (
        <InsufficientTable
          rows={scores.insufficient}
          priceDate={scores.meta.scoring_date}
          priorDate={scores.meta.prior_scoring_date}
        />
      ) : (
        <>
          {/* Names the table and the scope, so the heading always says what the rows are. */}
          <div className="mainlabel">
            {segmentTitle(scores.segments_meta, app.segment)} ·{" "}
            {app.scope === "top_decile" ? "Top 10% per sector" : "All"}{" "}
            <span className="mono">({visible.length.toLocaleString()})</span>
          </div>
          <RankTable
            rows={visible}
            metrics={scores.metrics}
            factors={scores.factors}
            history={history.tickers}
            scrollRef={scrollRef}
            tag="main"
            emptyState={<EmptyResult scope={app.scope} noun={segmentNoun(app.segment)} />}
          />
          {app.scope === "top_decile" && visible.length > 0 && (
            <p className="note" style={{ margin: "10px 18px 0", maxWidth: "80ch" }}>
              Showing the top decile within each sector ({visible.length} of {ranked.length} scored
              stocks in this table). A global top-N would be dominated by whichever sectors score
              high on absolute metrics and can erase entire sectors, so the default cut is
              per-sector. Switch to “All {segmentNoun(app.segment)}” in the toolbar to see every one.
            </p>
          )}
        </>
      )}
      <FooterNote scores={scores} />
    </Shell>
  );
}

function EmptyResult({ scope, noun }: { scope: string; noun: string }) {
  return (
    <div className="emptyq">
      <strong>No stocks match the current filters.</strong>
      {scope === "top_decile"
        ? `You are viewing the top 10% of each sector — switch to “All ${noun}”, or clear a filter.`
        : "Try clearing a filter or widening a score range."}
    </div>
  );
}

/** The selected table's full name for the heading, e.g. "Operating companies". */
function segmentTitle(meta: SegmentMeta[], segment: string): string {
  return meta.find((m) => m.key === segment)?.label ?? segment;
}

function InsufficientTable({
  rows,
  priceDate,
  priorDate,
}: {
  rows: InsufficientRow[];
  priceDate: string;
  priorDate: string;
}) {
  const { query, sectors } = useApp();
  const shown = rows.filter((r) => {
    if (sectors.length && !sectors.includes(r.sector ?? "(unclassified)")) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    return r.ticker.toLowerCase().includes(q) || r.name.toLowerCase().includes(q);
  });
  return (
    <>
      <div className="mainlabel">
        Insufficient data · unranked <span className="mono">({shown.length.toLocaleString()})</span>
      </div>
      <p className="note" style={{ margin: "0 18px", maxWidth: "82ch" }}>
        These stocks resolved too few of their applicable metrics to be scored. They are{" "}
        <b>unranked, not low-ranked</b> — a stock scored on three of eleven metrics would carry a
        number that looks like a judgement and is not one. Each row names what was missing and why.
      </p>
      <div className="twrap">
        <table>
          <colgroup>
            <col style={{ width: 84 }} />
            <col style={{ width: 190 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 74 }} />
            <col style={{ width: 76 }} />
            <col style={{ width: 76 }} />
            <col />
          </colgroup>
          <thead>
            <tr>
              <th className="al-l">Ticker</th>
              <th className="al-l">Company</th>
              <th className="al-l">Sector</th>
              <th className="al-r">Cap</th>
              <th className="al-r" title="Closing price on the scoring date. Prices update once a month.">
                Price<span className="thsub">{dayMonth(priceDate)}</span>
              </th>
              <th className="al-r" title="Price change from the previous scoring date to this one">
                1-Mo %<span className="thsub">{monthShort(priorDate)}→{monthShort(priceDate)}</span>
              </th>
              <th className="al-l">Why it is unranked</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.ticker} style={{ cursor: "default" }}>
                <td className="al-l tk">{row.ticker}</td>
                <td className="al-l nm" title={row.name}>{cleanName(row.name)}</td>
                <td className="al-l sec">{row.sector}</td>
                <td className="al-r mono">{marketCap(row.market_cap)}</td>
                <td className="al-r mono">${row.price.toFixed(2)}</td>
                <td className="al-r mono">{percent(row.price_change_pct)}</td>
                <td className="al-l" style={{ whiteSpace: "normal", fontSize: 11.5, color: "var(--ink-2)" }}>
                  {row.reason}
                  {row.missing.length > 0 && (
                    <>
                      {" — missing: "}
                      {row.missing.join(", ")}
                    </>
                  )}
                </td>
              </tr>
            ))}
            {!shown.length && (
              <tr>
                <td colSpan={7}>
                  <div className="emptyq">
                    <strong>Nothing here.</strong>
                    Every stock that reached this stage resolved enough metrics to be scored.
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function FooterNote({ scores }: { scores: ScoresPayload }) {
  return (
    <p className="note" style={{ margin: "18px 18px 0", maxWidth: "84ch" }}>
      Operating companies, banks and insurers, REITs, and pre-revenue biotech are scored in four
      separate tables and are never ranked against each other, on metrics each of them actually
      reports: a bank legitimately has no gross margin, and a REIT&apos;s profit is depressed by
      depreciation on buildings that hold their value, so it is scored on funds from operations.
      Weights v{scores.meta.weights_version}, effective for this run and stamped onto every stored
      score.
    </p>
  );
}

type AppState = ReturnType<typeof useApp>;

function filterAndSort(rows: RankedRow[], app: AppState): RankedRow[] {
  const q = app.query.trim().toLowerCase();
  const filtered = rows.filter((row) => {
    if (q && !row.ticker.toLowerCase().includes(q) && !row.name.toLowerCase().includes(q)) return false;
    if (app.sectors.length && !app.sectors.includes(row.sector ?? "(unclassified)")) return false;
    if (app.chgMin > CHG_ANY && (row.price_change_pct == null || row.price_change_pct < app.chgMin)) return false;
    if (app.ranges.composite > 0 && (row.liveComposite == null || row.liveComposite < app.ranges.composite)) return false;
    for (const key of ["quality", "growth", "valuation", "health"] as const) {
      const min = app.ranges[key];
      if (min > 0 && (row.factors[key] == null || row.factors[key]! < min)) return false;
    }
    // The default view is the top decile within each sector, not a global cut.
    // Search always looks across the whole segment - a user typing a ticker
    // expects to find it.
    if (app.scope === "top_decile" && !q && (row.sector_decile ?? 99) > 1) return false;
    return true;
  });

  const column = app.sortKey;
  const dir = app.sortDir;
  const get = (row: RankedRow): number | string | null => {
    switch (column) {
      case "composite":
        return row.liveComposite;
      case "_rank":
        return row.liveRank;
      case "quality":
      case "growth":
      case "valuation":
      case "health":
        return row.factors[column];
      case "_stability":
        return row.stability?.score ?? null;
      default:
        return (row as unknown as Record<string, number | string | null>)[column] ?? null;
    }
  };

  return filtered.sort((a, b) => {
    const av = get(a);
    const bv = get(b);
    if (typeof av === "string" || typeof bv === "string") {
      return dir * String(av ?? "").localeCompare(String(bv ?? ""));
    }
    if (av == null) return 1;   // missing values sort last in both directions
    if (bv == null) return -1;
    return dir * (av - bv);
  });
}
