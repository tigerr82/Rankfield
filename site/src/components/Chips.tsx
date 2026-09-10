import type { FactorSpec } from "../data/types";
import { CHG_ANY, useApp, type Ranges } from "../state/AppState";
import { isDefaultWeights } from "../lib/scoring";
import { Link } from "react-router-dom";

/** Active filters as removable chips above the table, with one "clear all" —
 *  no constraint is ever applied without a visible way to remove it. */
export function Chips({ factors }: { factors: FactorSpec[] }) {
  const { sectors, toggleSector, ranges, setRange, chgMin, setChgMin, query, setQuery,
          clearFilters, hasFilters, weights, resetWeights } = useApp();

  const labels: Record<string, string> = { composite: "Score" };
  for (const f of factors) labels[f.key] = f.label;

  const whatIf = !isDefaultWeights(weights);
  if (!hasFilters && !whatIf) return null;

  return (
    <div className="chips">
      {whatIf && (
        <span className="chip" style={{ borderColor: "var(--accent)" }}>
          <Link to="/weights" style={{ textDecoration: "none", color: "inherit" }}>
            What-if weights: {factors.map((f) => `${weights[f.key]}`).join("/")} — exploratory, not saved
          </Link>
          <button type="button" onClick={resetWeights} aria-label="Reset to official weights">
            ×
          </button>
        </span>
      )}
      {query && (
        <span className="chip">
          “{query}”
          <button type="button" onClick={() => setQuery("")} aria-label="Clear search">
            ×
          </button>
        </span>
      )}
      {sectors.map((sector) => (
        <span className="chip" key={sector}>
          {sector}
          <button type="button" onClick={() => toggleSector(sector)} aria-label={`Remove ${sector} filter`}>
            ×
          </button>
        </span>
      ))}
      {Object.entries(ranges)
        .filter(([, v]) => v > 0)
        .map(([key, value]) => (
          <span className="chip" key={key}>
            {labels[key] ?? key} ≥ {value}
            <button
              type="button"
              onClick={() => setRange(key as keyof Ranges, 0)}
              aria-label={`Remove ${labels[key] ?? key} filter`}
            >
              ×
            </button>
          </span>
        ))}
      {chgMin > CHG_ANY && (
        <span className="chip">
          1-month change ≥ {chgMin > 0 ? "+" : ""}
          {chgMin}%
          <button type="button" onClick={() => setChgMin(CHG_ANY)} aria-label="Remove price change filter">
            ×
          </button>
        </span>
      )}
      {hasFilters && (
        <button type="button" className="linkbtn" style={{ alignSelf: "center" }} onClick={clearFilters}>
          Clear all
        </button>
      )}
    </div>
  );
}
