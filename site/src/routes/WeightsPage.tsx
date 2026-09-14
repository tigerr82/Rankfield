import { useMemo } from "react";
import { usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";
import { RankTable } from "../components/RankTable";
import { TableSkeleton } from "../components/Skeleton";
import { DEFAULT_WEIGHTS, formatWeight, isDefaultWeights, rankDisplacement, rankRows } from "../lib/scoring";
import { useApp } from "../state/AppState";
import type { SegmentKey } from "../data/types";

/**
 * What-if weighting.
 *
 * Factor percentiles are precomputed and shipped in the payload, so re-weighting
 * is a weighted average of numbers already in the browser: no re-run, no
 * refetch, no server call. It is session-only and never writes to history.
 * Official weights live in config/weights.json and change rarely and
 * deliberately; bumping that version starts a new series rather than re-scoring
 * the past.
 */
export function WeightsPage() {
  const { scores, history, loading } = usePayload();
  const scrollRef = useScrollRef();
  const { weights, setWeight, resetWeights, segment } = useApp();

  const rows = useMemo(
    () => (scores ? scores.segments[(segment === "insufficient" ? "operating" : segment) as SegmentKey] ?? [] : []),
    [scores, segment],
  );
  const official = scores?.meta.weights;
  const ranked = useMemo(() => rankRows(rows, weights, official), [rows, weights, official]);
  const moved = useMemo(
    () => (rows.length ? rankDisplacement(rows, weights, official) : 0),
    [rows, weights, official],
  );

  if (loading || !scores || !history) {
    return (
      <Shell scrollRef={scrollRef}>
        <TableSkeleton rows={8} />
      </Shell>
    );
  }

  return (
    <Shell scrollRef={scrollRef}>
      <div className="card">
        <div className="sechead">
          <h2 style={{ fontFamily: "var(--font-head)", textTransform: "none", letterSpacing: 0, fontSize: 20, fontWeight: 500 }}>
            Score weights
          </h2>
          <span className="meta">
            official: v{scores.meta.weights_version} ·{" "}
            {Object.entries(scores.meta.weights).map(([, v]) => v).join("/")}
          </span>
        </div>
        <p className="note">
          Adjusting these re-ranks the table below instantly — the factor percentiles are already in
          the browser, so this is arithmetic, not a new run.{" "}
          <b>Changes here affect this session only.</b> They never write to score history and never
          alter the stored monthly records, which keep the official weights that produced them.
        </p>
        <div className="wgrid">
          {scores.factors.map((factor) => (
            <div className="wsl" key={factor.key}>
              <div className="top">
                <span>{factor.label}</span>
                <b>{formatWeight(weights[factor.key])}%</b>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={weights[factor.key]}
                onChange={(e) => setWeight(factor.key, Number(e.target.value))}
                aria-label={`${factor.label} weight`}
              />
            </div>
          ))}
        </div>
        <div className="wfoot">
          <button type="button" className="pillbtn" onClick={resetWeights}>
            Reset to {Object.values(DEFAULT_WEIGHTS).join("/")}
          </button>
          <span title="The difference is split equally across the other three. A weight that reaches 0 stops there and the rest absorb the remainder.">
            Total always 100% — moving one weight shifts the other three equally
          </span>
          <span>
            {isDefaultWeights(weights) ? (
              "Official weighting — ranking unchanged."
            ) : (
              <>
                <span className="warnv">{moved.toLocaleString()}</span> of {rows.length.toLocaleString()}{" "}
                stocks change rank versus the official weighting.
              </>
            )}
          </span>
        </div>
      </div>

      <p className="note" style={{ margin: "16px 18px 0", maxWidth: "84ch" }}>
        A stock that only ranks highly under one specific configuration is a weaker signal than one
        that ranks highly across many. The <b>Stable</b> column and the{" "}
        <a href="#/stability">stability view</a> quantify exactly that.
      </p>

      <RankTable
        rows={ranked}
        metrics={scores.metrics}
        factors={scores.factors}
        history={history.tickers}
        scrollRef={scrollRef}
        tag="weights"
      />
    </Shell>
  );
}
