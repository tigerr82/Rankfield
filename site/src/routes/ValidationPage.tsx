import { useMemo, useState } from "react";
import { usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";
import { decileAnalysis, MIN_OBSERVATIONS, type ValidationResult } from "../lib/analytics";
import { percent } from "../lib/format";

/**
 * Score versus price - the only question that ultimately matters.
 *
 * Built to refuse the confident-nonsense version of itself:
 *   - level at month T to forward return, never change against change;
 *   - reported per factor, with Value flagged as price-contaminated by
 *     construction (its score mechanically rises when price falls);
 *   - every figure benchmarked against the universe average over the identical
 *     window, with the observation count shown;
 *   - below MIN_OBSERVATIONS monthly observations, no correlation figure is
 *     rendered at all.
 */
export function ValidationPage() {
  const { scores, history, loading } = usePayload();
  const scrollRef = useScrollRef();
  const [horizon, setHorizon] = useState(3);

  const results = useMemo<ValidationResult[]>(() => {
    if (!scores || !history) return [];
    return [
      decileAnalysis(history, "composite", "Rankfield Score", false, horizon),
      ...scores.factors.map((f) =>
        decileAnalysis(history, f.key, f.label, f.price_dependent, horizon),
      ),
    ];
  }, [scores, history, horizon]);

  const observations = results[0]?.observations ?? 0;
  const monthsHeld = history?.months.length ?? 0;

  return (
    <Shell scrollRef={scrollRef}>
      <div className="prose">
        <h1>Does the score predict anything?</h1>
        <p className="lede">
          Each monthly record stores both the scores and the adjusted close on the scoring date.
          That pairing is what lets this question be answered — stocks scoring X at month T, what did
          they return over the months that followed?
        </p>

        {loading && <p>Loading history…</p>}

        {!loading && observations < MIN_OBSERVATIONS && (
          <div className="callout caution">
            <b>Not enough history yet to interpret.</b> This view needs at least{" "}
            {MIN_OBSERVATIONS} monthly observations before any result can be read as evidence, and
            there {monthsHeld === 1 ? "is" : "are"} currently <b>{monthsHeld}</b> stored{" "}
            {monthsHeld === 1 ? "month" : "months"} of scores ({observations} usable{" "}
            {horizon}-month {observations === 1 ? "window" : "windows"}). The scarce dimension here
            is time — twelve observations a year — not stocks: a decile already holds hundreds of
            names, so the cross-sectional sample is healthy immediately.
            <br />
            <br />
            The plumbing is running from run 1: <code>data/history/scores_YYYY-MM.json</code> gains a
            file each month and never loses one. A month not captured is a month of track record
            permanently lost, which is why history ships before the charts that display it. Come
            back around <b>{MIN_OBSERVATIONS + horizon} runs in</b>.
          </div>
        )}

        <h2>How this will be read, when there is enough of it</h2>
        <p>
          Deciles, not a scatter of thousands of points, and all ten of them — a clean monotonic
          progression from decile 1 to decile 10 is what would make the result credible, and its
          absence is itself informative.
        </p>

        <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "0 0 14px" }}>
          <span className="uppercase">Horizon</span>
          {[1, 3, 6, 12].map((h) => (
            <button
              key={h}
              type="button"
              className={`pillbtn${horizon === h ? " on" : ""}`}
              onClick={() => setHorizon(h)}
            >
              {h} month{h === 1 ? "" : "s"}
            </button>
          ))}
        </div>

        {results.map((result) => (
          <DecileTable key={result.key} result={result} />
        ))}

        <h2>Two rules this view will not break</h2>
        <p>
          <b>Value is contaminated by construction.</b> EBIT/EV, EBITDA/EV and FCF/EV all contain
          price in the denominator. When a stock falls, its Value score mechanically rises and the
          composite rises with it, so correlating the composite against price yields a strong
          relationship that is pure arithmetic rather than predictive power. Quality, Growth and
          Financial Health contain no price at all — their results are the meaningful ones.
        </p>
        <p>
          <b>History is never re-scored.</b> Changing the weights starts a new series; the old one
          stays exactly as it was. Re-scoring the past with today&apos;s weights guarantees a
          flattering backtest and destroys the evidential value of the whole exercise.
        </p>
        <p>
          Momentum is deliberately excluded from the score, partly for this reason: momentum is
          entirely price, so including it would mean partly testing whether past price predicts
          future price — obscuring the question this page exists to answer.
        </p>
      </div>
    </Shell>
  );
}

function DecileTable({ result }: { result: ValidationResult }) {
  const hasData = result.buckets.some((b) => b.meanForwardReturn != null);
  return (
    <div style={{ marginBottom: 22 }}>
      <h3>
        {result.label}
        {result.priceDependent && (
          <span className="basis inv" style={{ marginLeft: 8, fontSize: 10 }}>
            PRICE-CONTAMINATED
          </span>
        )}
      </h3>
      {result.priceDependent && (
        <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: "0 0 8px" }}>
          Built from price-based multiples, so any relationship with price is partly definitional.
          Not evidence of prediction.
        </p>
      )}
      {!hasData ? (
        <div className="callout">
          No completed {result.horizonMonths}-month windows yet — this table populates once{" "}
          {result.horizonMonths + 1} monthly runs have been stored.
        </div>
      ) : (
        <>
          <table>
            <thead>
              <tr>
                <th className="al-l">Decile</th>
                <th className="al-r">Mean {result.horizonMonths}-mo return</th>
                <th className="al-r">Spread vs universe</th>
                <th className="al-r">Stock-months</th>
              </tr>
            </thead>
            <tbody>
              {result.buckets.map((bucket) => (
                <tr key={bucket.decile} style={{ cursor: "default" }}>
                  <td className="al-l">{bucket.decile === 1 ? "1 (highest)" : bucket.decile === 10 ? "10 (lowest)" : bucket.decile}</td>
                  <td className="al-r mono">{percent(bucket.meanForwardReturn)}</td>
                  <td className="al-r mono">
                    {percent(
                      bucket.meanForwardReturn != null && result.universeMean != null
                        ? bucket.meanForwardReturn - result.universeMean
                        : null,
                    )}
                  </td>
                  <td className="al-r mono">{bucket.count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
            Universe average {percent(result.universeMean)} over the identical window ·{" "}
            {result.observations} monthly observation{result.observations === 1 ? "" : "s"} ·{" "}
            {result.monotonic ? "progression is monotonic across all ten deciles" : "progression is not monotonic"}.
            {!result.interpretable && (
              <>
                {" "}
                <b>Below {MIN_OBSERVATIONS} monthly observations this is too small a sample to
                interpret</b> — shown for transparency, not as a finding.
              </>
            )}
          </p>
        </>
      )}
    </div>
  );
}
