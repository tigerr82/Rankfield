import { useCallback, useMemo, useRef, useState, type RefObject } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { HistoryPoint, MetricSpec, FactorSpec } from "../data/types";
import type { RankedRow } from "../lib/scoring";
import { useApp } from "../state/AppState";
import { activeColumns, type Column } from "./columns";
import { RowExpansion } from "./RowExpansion";

const MIN_W = 32;
const ROW_H = 34;
/** Below this, rendering every row outright is cheaper than virtualising it. */
const VIRTUALIZE_ABOVE = 60;

interface Props {
  rows: RankedRow[];
  metrics: MetricSpec[];
  factors: FactorSpec[];
  history: Record<string, HistoryPoint[]>;
  scrollRef: RefObject<HTMLElement | null>;
  /** Namespaces the expansion state so the portfolio and main tables can both
   *  be open without fighting each other. */
  tag: string;
  className?: string;
  emptyState?: React.ReactNode;
}

export function RankTable({ rows, metrics, factors, history, scrollRef, tag, className, emptyState }: Props) {
  const { mode, hiddenColumns, widths, setWidths, sortKey, sortDir, setSort, holdings, toggleHolding } = useApp();
  const [open, setOpen] = useState<string | null>(null);
  const columns = useMemo(() => activeColumns(mode, hiddenColumns), [mode, hiddenColumns]);
  const heldSet = useMemo(() => new Set(holdings), [holdings]);

  const ctx = useMemo(
    () => ({
      isHeld: (t: string) => heldSet.has(t),
      toggleHolding,
      history,
      totalRows: rows.length,
    }),
    [heldSet, toggleHolding, history, rows.length],
  );

  // Flatten rows and any open expansion into one item list so the virtualizer
  // measures the expansion like any other item.
  const items = useMemo(() => {
    const out: { kind: "row" | "exp"; row: RankedRow }[] = [];
    for (const row of rows) {
      out.push({ kind: "row", row });
      if (open === `${tag}:${row.ticker}`) out.push({ kind: "exp", row });
    }
    return out;
  }, [rows, open, tag]);

  const virtualize = items.length > VIRTUALIZE_ABOVE;
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (i) => (items[i]?.kind === "exp" ? 300 : ROW_H),
    overscan: 12,
    enabled: virtualize,
  });

  const virtualItems = virtualize ? virtualizer.getVirtualItems() : [];
  const paddingTop = virtualize && virtualItems.length ? virtualItems[0].start : 0;
  const paddingBottom =
    virtualize && virtualItems.length
      ? virtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end
      : 0;
  const visible = virtualize ? virtualItems.map((v) => ({ index: v.index, ...items[v.index] })) : items.map((it, index) => ({ index, ...it }));

  const toggleRow = useCallback((ticker: string) => {
    setOpen((prev) => (prev === `${tag}:${ticker}` ? null : `${tag}:${ticker}`));
  }, [tag]);

  return (
    <div className={`twrap ${className ?? ""}`}>
      <table>
        <colgroup>
          {columns.map((c) => (
            <col key={c.key} style={{ width: `${widths[c.key] ?? c.width}px` }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((c, i) => (
              <HeaderCell
                key={c.key}
                column={c}
                isLast={i === columns.length - 1}
                sorted={sortKey === c.key ? sortDir : 0}
                onSort={() => !c.nosort && setSort(c.key)}
                columns={columns}
                widths={widths}
                setWidths={setWidths}
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {paddingTop > 0 && (
            <tr className="spacer" aria-hidden="true">
              <td colSpan={columns.length} style={{ height: paddingTop }} />
            </tr>
          )}
          {visible.map((item) =>
            item.kind === "row" ? (
              <tr
                key={`r-${item.row.ticker}`}
                data-index={item.index}
                ref={virtualize ? virtualizer.measureElement : undefined}
                className={open === `${tag}:${item.row.ticker}` ? "open" : ""}
                onClick={() => toggleRow(item.row.ticker)}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggleRow(item.row.ticker);
                  }
                }}
                aria-expanded={open === `${tag}:${item.row.ticker}`}
              >
                {columns.map((c) => (
                  <td key={c.key} data-col={c.key} className={`al-${c.align}${c.cls ? ` ${c.cls}` : ""}`}>
                    {c.render(item.row, ctx)}
                  </td>
                ))}
              </tr>
            ) : (
              <tr
                key={`e-${item.row.ticker}`}
                data-index={item.index}
                ref={virtualize ? virtualizer.measureElement : undefined}
                className="exp"
              >
                <td colSpan={columns.length}>
                  <RowExpansion row={item.row} metrics={metrics} factors={factors} history={history[item.row.ticker] ?? []} />
                </td>
              </tr>
            ),
          )}
          {paddingBottom > 0 && (
            <tr className="spacer" aria-hidden="true">
              <td colSpan={columns.length} style={{ height: paddingBottom }} />
            </tr>
          )}
          {!rows.length && (
            <tr className="spacer">
              <td colSpan={columns.length}>{emptyState ?? <DefaultEmpty />}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function DefaultEmpty() {
  return (
    <div className="emptyq">
      <strong>No stocks match the current filters.</strong>
      Widen a range in the filter rail, or clear all filters to see the full table.
    </div>
  );
}

interface HeaderProps {
  column: Column;
  isLast: boolean;
  sorted: number;
  onSort: () => void;
  columns: Column[];
  widths: Record<string, number>;
  setWidths: (widths: Record<string, number>) => void;
}

function HeaderCell({ column, isLast, sorted, onSort, columns, widths, setWidths }: HeaderProps) {
  const dragging = useRef<{ startX: number; startW: number; nextKey: string | null; nextW: number } | null>(null);

  const onPointerDown = (e: React.PointerEvent<HTMLSpanElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    const idx = columns.findIndex((c) => c.key === column.key);
    const next = idx >= 0 && idx < columns.length - 1 ? columns[idx + 1] : null;
    dragging.current = {
      startX: e.clientX,
      startW: widths[column.key] ?? column.width,
      nextKey: next?.key ?? null,
      nextW: next ? widths[next.key] ?? next.width : 0,
    };
    handle.classList.add("act");
    document.body.classList.add("resizing");
  };

  const onPointerMove = (e: React.PointerEvent<HTMLSpanElement>) => {
    const drag = dragging.current;
    if (!drag) return;
    // Clamp so neither this column nor its neighbour drops below the minimum,
    // and keep the pair's total constant so the table does not reflow.
    let dx = Math.round(e.clientX - drag.startX);
    dx = Math.max(dx, MIN_W - drag.startW);
    if (drag.nextKey) dx = Math.min(dx, drag.nextW - MIN_W);
    const next = { ...widths, [column.key]: drag.startW + dx };
    if (drag.nextKey) next[drag.nextKey] = drag.nextW - dx;
    setWidths(next);
  };

  const endDrag = (e: React.PointerEvent<HTMLSpanElement>) => {
    dragging.current = null;
    e.currentTarget.classList.remove("act");
    document.body.classList.remove("resizing");
  };

  return (
    <th
      className={`${column.sticky ? "stick " : ""}al-${column.align}${sorted ? " srt" : ""}`}
      style={{ cursor: column.nosort ? "default" : "pointer" }}
      onClick={onSort}
      title={column.title}
      scope="col"
      aria-sort={sorted ? (sorted < 0 ? "descending" : "ascending") : "none"}
    >
      {column.header}
      {sorted !== 0 && <span className="ar">{sorted < 0 ? "▼" : "▲"}</span>}
      {!isLast && (
        <span
          className="rz"
          role="separator"
          aria-label={`Resize ${column.title}`}
          title="Drag to resize · double-click to reset all widths"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onClick={(e) => e.stopPropagation()}
          onDoubleClick={(e) => {
            e.stopPropagation();
            setWidths({});
          }}
        />
      )}
    </th>
  );
}
