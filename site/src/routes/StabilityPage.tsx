import { useMemo, useState } from "react";
import { usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";
import { StabilityCell } from "../components/cells";
import { cleanName } from "../components/columns";
import type { SegmentKey } from "../data/types";
import { useApp } from "../state/AppState";

/**
 * Stability across methodology - "good, or only good under these exact weights?"
 *
 * Computed within a single run by sweeping each factor weight across a plausible
 * range and re-ranking, so it is available from run 1. Distinct from stability
 * through time, which needs months to accumulate; the two answer different
 * questions and are deliberately not conflated.
 */
export function StabilityPage() {
  const { scores, loading } = usePayload();
  const scrollRef = useScrollRef();
  const { segment } = useApp();
  const [sort, setSort] = useState<"stable" | "volatile">("stable");

  const rows = useMemo(() => {
    if (!scores) return [];
    const source = scores.segments[(segment === "insufficient" ? "operating" : segment) as SegmentKey] ?? [];
    return [...source]
      .filter((r) => r.stability)
      .sort((a, b) =>
        sort === "stable"
          ? b.stability!.score - a.stability!.score
          : a.stability!.score - b.stability!.score,
      )
      .slice(0, 60);
  }, [scores, segment, sort]);

  const sweep = scores?.meta.settings.scoring.stability_sweep ?? [];
  const tested = scores ? rows[0]?.stability?.weightings_tested ?? 0 : 0;

  return (
    <Shell scrollRef={scrollRef}>
      <div className="prose" style={{ maxWidth: "100ch" }}>
        <h1>Rank stability</h1>
        <p className="lede">
          Every factor weight swept across {sweep.join(", ")}%, keeping the four weights summing to
          100 — {tested} plausible weightings in all. For each stock, the range its rank travels
          across them.
        </p>
        <div className="callout">
          A stock that sits in the top quintile under nearly any sensible weighting is materially
          different from one that is top-quintile only at the default 25/25/25/25. No competing
          product exposes this, and it costs one sweep per run to compute.
        </div>

        <div style={{ display: "flex", gap: 8, margin: "0 0 14px" }}>
          <button type="button" className={`pillbtn${sort === "stable" ? " on" : ""}`} onClick={() => setSort("stable")}>
            Most stable
          </button>
          <button type="button" className={`pillbtn${sort === "volatile" ? " on" : ""}`} onClick={() => setSort("volatile")}>
            Most weight-sensitive
          </button>
        </div>

        {loading && <p>Loading…</p>}

        {!loading && (
          <table>
            <thead>
              <tr>
                <th className="al-r">Rank</th>
                <th className="al-l">Ticker</th>
                <th className="al-l">Company</th>
                <th className="al-l">Rank range</th>
                <th className="al-r">Score</th>
                <th className="al-l">Reading</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ticker} style={{ cursor: "default" }}>
                  <td className="al-r rk">{row.rank}</td>
                  <td className="al-l tk">{row.ticker}</td>
                  <td className="al-l nm">{cleanName(row.name)}</td>
                  <td className="al-l">
                    <StabilityCell stability={row.stability} total={rows.length ? row.rank * 2 : 1} />
                  </td>
                  <td className="al-r mono">{row.composite?.toFixed(1) ?? "—"}</td>
                  <td className="al-l" style={{ whiteSpace: "normal", fontSize: 12 }}>
                    Ranks between {row.stability!.rank_min} and {row.stability!.rank_max} across{" "}
                    {row.stability!.weightings_tested} plausible weightings.
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Shell>
  );
}
