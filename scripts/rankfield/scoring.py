"""Winsorize -> sector-relative percentile -> factor -> composite, plus the
weight-sensitivity sweep.

Two rules shape everything here:

1. Nothing is ever ranked across the whole market. A bank's leverage and a
   software company's leverage are not comparable, so every percentile is taken
   within a cohort of the stock's own sector, inside its own model-validity
   segment.
2. Missing is missing. A metric that could not be computed is dropped from its
   factor and the remaining metrics carry the factor; a factor with no metrics
   at all is dropped from the composite and the remaining factor weights are
   renormalised. Nothing is imputed as zero.
"""
from __future__ import annotations

import itertools
import re
from statistics import median

from .metrics import FACTOR_KEYS, METRICS, METRICS_BY_KEY
from .util import mean, percentile_ranks, winsorize

# ------------------------------------------------------------- segmentation

SEGMENTS = {
    "operating": "Operating companies",
    "financials": "Financials & REITs",
    "pre_revenue": "Pre-revenue / biotech",
}

FINANCIAL_SECTORS = {"Finance", "Real Estate"}

# The sector label alone is not enough. The Nasdaq screener files ten education
# operators (Grand Canyon, Stride, Perdoceo, Strayer) under "Real Estate" with
# the industry "Other Consumer Services", and homebuilders alongside REITs.
# Segmenting on sector alone put those ordinary operating companies at the top
# of the Financials table - exactly the cross-sector comparison this whole
# design exists to prevent. So membership is confirmed against the industry
# label, which is specific where the sector label is not.
FINANCIAL_INDUSTRY = re.compile(
    r"(bank|insur|invest|financ|broker|savings institution|real estate|"
    r"trusts except|building operators)",
    re.IGNORECASE,
)
BIOTECH_INDUSTRY = re.compile(r"(biotechnolog|pharmaceutical preparation|medicinal chemical)", re.IGNORECASE)
PRE_REVENUE_CEILING = 10_000_000  # annualised revenue below which a biotech is pre-revenue


def classify_segment(listing: dict, revenue_ttm: float | None) -> str:
    """Model validity, the most important filter.

    The four factors assume a normal operating company. Banks, insurers, REITs
    and BDCs break them structurally - JPMorgan legitimately has no gross margin
    and no meaningful current ratio - and pre-revenue biotech breaks growth and
    valuation the same way. These are ranked in their own tables, never against
    an industrial.
    """
    sector = listing.get("sector") or ""
    industry = listing.get("industry") or ""
    if sector in FINANCIAL_SECTORS and FINANCIAL_INDUSTRY.search(industry):
        return "financials"
    if BIOTECH_INDUSTRY.search(industry):
        if revenue_ttm is None or revenue_ttm < PRE_REVENUE_CEILING:
            return "pre_revenue"
    return "operating"


# ---------------------------------------------------------------- scoring


def applicable_metrics(rows: list[dict], *, min_resolution: float = 0.40) -> tuple[list[str], dict]:
    """Which metrics this segment can actually be scored on.

    A metric that almost nobody in the segment resolves is structurally
    inapplicable to it (gross profits for banks, for instance), not a data
    failure by each individual company. Excluding it from the segment's
    coverage denominator is what stops an entire sector being labelled
    "insufficient data" for a reason that is really about the model.
    """
    total = len(rows) or 1
    resolution = {}
    keys = []
    segment = rows[0].get("segment") if rows else None
    for m in METRICS:
        if segment in m.get("not_for_segments", ()):
            resolution[m["key"]] = 0.0
            continue
        n = sum(1 for r in rows if r["values"].get(m["key"]) is not None)
        resolution[m["key"]] = round(n / total, 3)
        if n / total >= min_resolution:
            keys.append(m["key"])
    return keys, resolution


def score_segment(
    rows: list[dict],
    *,
    weights: dict[str, float],
    winsor: tuple[float, float],
    roic_hurdle: float,
    min_cohort: int,
    coverage_threshold: float,
    metric_applicability: float = 0.40,
) -> dict:
    """Score one model-validity segment. Returns scored rows and the rows
    routed out for insufficient coverage."""
    metric_keys, resolution = applicable_metrics(rows, min_resolution=metric_applicability)

    # ---- cohorts: sector within segment, with a documented fallback
    cohorts: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        cohorts.setdefault(r["listing"].get("sector") or "(unclassified)", []).append(i)
    small = [s for s, idx in cohorts.items() if len(idx) < min_cohort]
    fallback_idx = [i for s in small for i in cohorts[s]]
    for s in small:
        cohorts.pop(s)
    if fallback_idx:
        cohorts["(segment-wide)"] = fallback_idx

    percentiles: list[dict[str, float | None]] = [{} for _ in rows]
    bases: list[dict[str, str]] = [{} for _ in rows]

    for cohort_name, idx in cohorts.items():
        basis = "universe" if cohort_name == "(segment-wide)" else "sector"
        for key in metric_keys:
            spec = METRICS_BY_KEY[key]
            raw = [rows[i]["values"].get(key) for i in idx]
            clipped = winsorize(raw, winsor[0], winsor[1])
            ranked = percentile_ranks(clipped, spec["higher_better"])
            for pos, i in enumerate(idx):
                percentiles[i][key] = ranked[pos]
                bases[i][key] = basis

    # ---- growth is ROIC-conditioned, applied AFTER the percentile step.
    # The conditioned set is read from the registry rather than listed here, so
    # moving a metric between factors cannot leave it inverted by mistake.
    growth_keys = [m["key"] for m in METRICS if m["factor"] == "growth"]
    for i, r in enumerate(rows):
        roic = r["values"].get("roic")
        for key in growth_keys:
            p = percentiles[i].get(key)
            if p is None:
                continue
            if roic is None:
                # Growth cannot be judged without knowing whether it is funded
                # at a return above the cost of capital. Unknown is not a
                # licence to reward it, and inverting would punish arbitrarily,
                # so the metric drops out and Growth renormalises.
                percentiles[i][key] = None
                r["missing"].setdefault(key, "ROIC unavailable, so growth cannot be ROIC-conditioned")
            elif roic <= roic_hurdle:
                # Below the cost-of-capital hurdle growth is never rewarded: the
                # score cannot exceed the midpoint, and faster growth scores
                # lower, because growth funded below the cost of capital destroys
                # value.
                #
                # Until methodology 1.2 this was a straight inversion, 100 - p,
                # which also turned the fastest-SHRINKING companies into the best
                # "growers": G-III, revenue falling 2.9% a year, scored 88.6 on
                # Growth and ranked first of 1,191; 148 companies with shrinking
                # revenue scored 70 or more. min(p, 100 - p) keeps the penalty on
                # value-destroying expansion and removes the reward for decline.
                percentiles[i][key] = round(min(p, 100.0 - p), 1)
                bases[i][key] = bases[i].get(key, "sector") + "|below-hurdle"

    # ---- factors and composite
    scored, insufficient = [], []
    for i, r in enumerate(rows):
        # A coverage-optional metric counts toward coverage only where it
        # resolved, so its absence never drops a company that the other ten
        # metrics can score.
        applicable = [k for k in metric_keys
                      if not METRICS_BY_KEY[k].get("coverage_optional") or percentiles[i].get(k) is not None]
        resolved = [k for k in applicable if percentiles[i].get(k) is not None]
        coverage = len(resolved) / len(applicable) if applicable else 0.0

        factors: dict[str, float | None] = {}
        for factor in FACTOR_KEYS:
            in_factor = [
                percentiles[i][k]
                for k in applicable
                if METRICS_BY_KEY[k]["factor"] == factor and percentiles[i].get(k) is not None
            ]
            factors[factor] = round(mean(in_factor), 1) if in_factor else None

        record = {
            **r,
            "percentiles": {k: percentiles[i].get(k) for k in applicable},
            "bases": {k: bases[i].get(k) for k in applicable},
            "factors": factors,
            "coverage": round(coverage, 3),
            "applicable_metrics": applicable,
        }
        if coverage < coverage_threshold:
            record["insufficient_reason"] = (
                f"resolved {len(resolved)} of {len(applicable)} applicable metrics "
                f"({coverage:.0%}, threshold {coverage_threshold:.0%})"
            )
            insufficient.append(record)
        else:
            record["composite"] = composite_of(factors, weights)
            scored.append(record)

    scored.sort(key=lambda r: (r["composite"] is None, -(r["composite"] or 0)))
    for pos, r in enumerate(scored, start=1):
        r["rank"] = pos
    assign_sector_deciles(scored)
    return {
        "scored": scored,
        "insufficient": insufficient,
        "metric_resolution": resolution,
        "applicable_metrics": metric_keys,
        "cohorts": {name: len(idx) for name, idx in cohorts.items()},
    }


def composite_of(factors: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """Weighted blend of whichever factors exist, weights renormalised.

    This is the same arithmetic the browser runs when the what-if weight sliders
    move, which is why re-weighting never needs a re-run or a refetch.
    """
    total = 0.0
    weight = 0.0
    for key in FACTOR_KEYS:
        value = factors.get(key)
        w = weights.get(key, 0)
        if value is not None and w > 0:
            total += value * w
            weight += w
    return round(total / weight, 2) if weight else None


def assign_sector_deciles(scored: list[dict]) -> None:
    """Decile within the stock's own sector, so the default view can show the
    top decile per sector rather than a global top-N (a global cut is dominated
    by whichever sectors score high on absolute metrics and can erase others)."""
    by_sector: dict[str, list[dict]] = {}
    for r in scored:
        by_sector.setdefault(r["listing"].get("sector") or "(unclassified)", []).append(r)
    for rows in by_sector.values():
        ranked = sorted(
            [r for r in rows if r.get("composite") is not None],
            key=lambda r: -r["composite"],
        )
        n = len(ranked)
        for pos, r in enumerate(ranked):
            r["sector_decile"] = min(10, int(pos / n * 10) + 1) if n else None
            r["sector_rank"] = pos + 1
            r["sector_size"] = n
        for r in rows:
            r.setdefault("sector_decile", None)


# ------------------------------------------------------- weight sensitivity


def weight_combinations(sweep: list[int]) -> list[dict[str, float]]:
    """Every plausible weighting: each factor swept across the range, keeping
    the four weights summing to 100."""
    combos = []
    for values in itertools.product(sweep, repeat=len(FACTOR_KEYS)):
        if sum(values) == 100:
            combos.append(dict(zip(FACTOR_KEYS, values)))
    return combos


def rank_stability(scored: list[dict], sweep: list[int]) -> None:
    """How much each stock's rank moves across plausible weightings.

    A stock that ranks highly under nearly any sensible weighting is a more
    robust signal than one that only ranks highly under this exact
    configuration. Computed within a single run, so it is available from run 1 -
    unlike stability through time, which needs months to accumulate.
    """
    combos = weight_combinations(sweep)
    if not combos or not scored:
        return
    ranks: dict[str, list[int]] = {r["ticker"]: [] for r in scored}
    for weights in combos:
        ordered = sorted(
            scored,
            key=lambda r: -(composite_of(r["factors"], weights) or -1),
        )
        for pos, r in enumerate(ordered, start=1):
            ranks[r["ticker"]].append(pos)
    n = len(scored)
    for r in scored:
        rs = ranks[r["ticker"]]
        r["stability"] = {
            "rank_min": min(rs),
            "rank_max": max(rs),
            "rank_median": int(median(rs)),
            "weightings_tested": len(combos),
            # 1.0 = rank never moves; 0 = it can span the whole table.
            "score": round(1 - (max(rs) - min(rs)) / max(n - 1, 1), 3),
        }
