import { useMemo, useState } from "react";
import { useCoverage, usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";

/**
 * The eligibility funnel and every unresolved metric, named. Publishing this is
 * the point: a screen that hides what it could not compute is asking to be
 * trusted rather than checked.
 */
export function CoveragePage() {
  const { coverage, loading, error } = useCoverage();
  const { scores } = usePayload();
  const scrollRef = useScrollRef();
  const [filter, setFilter] = useState("");

  const byReason = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of coverage?.unresolved_metrics ?? []) {
      counts.set(row.reason, (counts.get(row.reason) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [coverage]);

  const excluded = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const rows = coverage?.excluded ?? [];
    return q ? rows.filter((r) => r.ticker.toLowerCase().includes(q) || r.reason.toLowerCase().includes(q)) : rows;
  }, [coverage, filter]);

  return (
    <Shell scrollRef={scrollRef}>
      <div className="prose" style={{ maxWidth: "104ch" }}>
        <h1>Coverage report</h1>
        <p className="lede">
          What was scored, what was not, and why — with a count at every stage of the funnel. The
          same content is written to <code>data/coverage_report.json</code> on every run.
        </p>

        {loading && <p>Loading…</p>}
        {error && <div className="callout caution">Could not load the coverage report: {error}</div>}

        {coverage && (
          <>
            <h2>Eligibility funnel</h2>
            <table>
              <thead>
                <tr>
                  <th className="al-l">Stage</th>
                  <th className="al-r">Remaining</th>
                  <th className="al-r">Dropped</th>
                </tr>
              </thead>
              <tbody>
                {coverage.funnel.map((stage, i) => {
                  const prev = i > 0 ? coverage.funnel[i - 1].count : null;
                  const dropped = prev != null && !stage.stage.startsWith("segment:") ? prev - stage.count : null;
                  return (
                    <tr key={stage.stage} style={{ cursor: "default" }}>
                      <td className="al-l">{stage.stage}</td>
                      <td className="al-r mono">{stage.count.toLocaleString()}</td>
                      <td className="al-r mono" style={{ color: dropped ? "var(--ink-3)" : "transparent" }}>
                        {dropped != null && dropped > 0 ? `−${dropped.toLocaleString()}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <h2>Metric resolution by segment</h2>
            <p>
              A metric that almost nobody in a segment resolves is structurally inapplicable to it
              (gross profits for banks, for instance) rather than a data failure by each company, so
              it is excluded from that segment&apos;s coverage denominator. Without that, an entire
              sector would be labelled &ldquo;insufficient data&rdquo; for a reason that is really
              about the model.
            </p>
            {scores &&
              scores.segments_meta.map((segment) => (
                <div key={segment.key} style={{ marginBottom: 16 }}>
                  <h3>{segment.label}</h3>
                  <table>
                    <thead>
                      <tr>
                        <th className="al-l">Metric</th>
                        <th className="al-r">Resolved</th>
                        <th className="al-l">Applicable to this segment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scores.metrics.map((metric) => {
                        const share = segment.metric_resolution[metric.key];
                        const applicable = segment.applicable_metrics.includes(metric.key);
                        return (
                          <tr key={metric.key} style={{ cursor: "default" }}>
                            <td className="al-l">{metric.label}</td>
                            <td className="al-r mono">
                              {share != null ? `${Math.round(share * 100)}%` : "—"}
                            </td>
                            <td className="al-l" style={{ color: applicable ? "var(--ink-2)" : "var(--ink-3)" }}>
                              {applicable ? "yes" : "no — structurally inapplicable"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ))}

            <h2>Why metrics failed to resolve</h2>
            <table>
              <thead>
                <tr>
                  <th className="al-l">Reason</th>
                  <th className="al-r">Occurrences</th>
                </tr>
              </thead>
              <tbody>
                {byReason.slice(0, 25).map(([reason, count]) => (
                  <tr key={reason} style={{ cursor: "default" }}>
                    <td className="al-l">{reason}</td>
                    <td className="al-r mono">{count.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {coverage.price_review.length > 0 && (
              <>
                <h2>Flagged for corporate-action review</h2>
                <p>
                  Any monthly move beyond ±50% is logged: a corporate action is the far more likely
                  explanation than a real price move. Both endpoints are computed from today&apos;s
                  adjusted series, so a split alone should not produce one of these.
                </p>
                <table>
                  <thead>
                    <tr>
                      <th className="al-l">Ticker</th>
                      <th className="al-r">1-month change</th>
                      <th className="al-l">Splits in window</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coverage.price_review.map((row) => (
                      <tr key={row.ticker} style={{ cursor: "default" }}>
                        <td className="al-l tk">{row.ticker}</td>
                        <td className="al-r mono">{row.change_pct > 0 ? "+" : ""}{row.change_pct.toFixed(1)}%</td>
                        <td className="al-l mono" style={{ fontSize: 11 }}>
                          {row.splits_in_window.length
                            ? row.splits_in_window.map((s) => JSON.stringify(s)).join(", ")
                            : "none — treated as a genuine move"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}

            <h2>Excluded before scoring ({coverage.excluded.length.toLocaleString()})</h2>
            <input
              className="search"
              style={{ width: 280, marginBottom: 10 }}
              placeholder="Filter by ticker or reason…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <table>
              <thead>
                <tr>
                  <th className="al-l">Ticker</th>
                  <th className="al-l">Stage</th>
                  <th className="al-l">Reason</th>
                </tr>
              </thead>
              <tbody>
                {excluded.slice(0, 400).map((row) => (
                  <tr key={`${row.ticker}-${row.stage}`} style={{ cursor: "default" }}>
                    <td className="al-l tk">{row.ticker}</td>
                    <td className="al-l">{row.stage}</td>
                    <td className="al-l" style={{ whiteSpace: "normal", fontSize: 12 }}>{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {excluded.length > 400 && (
              <p style={{ color: "var(--ink-3)" }}>
                Showing the first 400 of {excluded.length.toLocaleString()} — filter above, or read{" "}
                <code>data/coverage_report.json</code> directly.
              </p>
            )}
          </>
        )}
      </div>
    </Shell>
  );
}
