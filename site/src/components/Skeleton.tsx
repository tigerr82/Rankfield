/** Loading state that holds the layout: the toolbar, the table frame and the
 *  row rhythm are all in place before data lands, so nothing jumps. */
export function TableSkeleton({ rows = 16 }: { rows?: number }) {
  const widths = [32, 42, 84, 168, 102, 68, 72, 76, 66];
  return (
    <>
      <div className="toolbar">
        <div className="skel" style={{ width: 96, height: 26 }} />
        <div className="skel" style={{ width: 210, height: 28 }} />
        <div className="skel" style={{ width: 260, height: 26 }} />
        <span className="count">
          <span className="skel" style={{ display: "inline-block", width: 110, height: 12 }} />
        </span>
      </div>
      <div className="twrap" aria-busy="true" aria-label="Loading rankings">
        <div className="skelrow" style={{ background: "var(--surface-2)" }}>
          {widths.map((w, i) => (
            <div className="skel" key={i} style={{ width: w, height: 9 }} />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, r) => (
          <div className="skelrow" key={r}>
            {widths.map((w, i) => (
              <div className="skel" key={i} style={{ width: w, height: 12, opacity: 1 - r * 0.045 }} />
            ))}
          </div>
        ))}
      </div>
    </>
  );
}
