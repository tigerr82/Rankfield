"""Stage 4 - eligibility funnel, scoring, history and the coverage report.

This is where the pieces meet: universe + prices + fundamentals go in, and the
scored tables, the append-only history record and the coverage report come out.

Two rules are enforced here rather than trusted elsewhere:

  * History is append-only. An existing month is never rewritten, and weights
    changes never re-score the past - bumping `weights_version` starts a new
    series and leaves the old one exactly as it was. Re-scoring history with
    today's weights guarantees a flattering backtest and destroys the
    evidential value of the entire exercise.
  * The prior month's price is recomputed from today's adjusted series, never
    read back from the stored record, so a split cannot manufacture a -90% move.

Run: python scripts/compute_scores.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import (
    DATA_DIR, HISTORY_DIR, ensure_dirs, load_settings, load_weights, read_json, write_json,
)
from rankfield.drift import build_drift_report
from rankfield.metrics import FACTORS, METRICS
from rankfield.scoring import SEGMENTS, classify_segment, rank_stability, score_segment
from rankfield.util import last_day_of_prior_month, month_key


def build_rows(universe, fundamentals, prices, settings, funnel, excluded):
    """Apply the structural-hygiene and liquidity filters, recording a count at
    every stage so the funnel is auditable."""
    cfg = settings["universe"]
    rows = []
    stage_counts = {"no_fundamentals": 0, "no_price": 0, "foreign_filer": 0,
                    "short_history": 0, "illiquid": 0}

    for listing in universe["listings"]:
        ticker = listing["ticker"]
        fund = fundamentals["companies"].get(ticker)
        price = prices["prices"].get(ticker)

        if not fund:
            stage_counts["no_fundamentals"] += 1
            excluded.append({"ticker": ticker, "stage": "fundamentals", "reason": "no XBRL facts on file"})
            continue
        if not price:
            stage_counts["no_price"] += 1
            excluded.append({"ticker": ticker, "stage": "price", "reason": "no adjusted close resolved"})
            continue
        if not fund["files_domestic_forms"]:
            stage_counts["foreign_filer"] += 1
            excluded.append({
                "ticker": ticker, "stage": "structural hygiene",
                "reason": f"files {', '.join(fund['forms']) or 'no periodic forms'}, not 10-K/10-Q "
                          "- different reporting cadence, not period-on-period comparable",
            })
            continue
        if fund["quarters_filed"] < cfg["min_quarters_filed"]:
            stage_counts["short_history"] += 1
            excluded.append({
                "ticker": ticker, "stage": "structural hygiene",
                "reason": f"only {fund['quarters_filed']} periodic filings on record under CIK "
                          f"{listing['cik']} (need {cfg['min_quarters_filed']}) - growth metrics unreliable",
            })
            continue
        adv = price.get("adv_dollar")
        if adv is None or adv < cfg["adv_dollar_floor"]:
            stage_counts["illiquid"] += 1
            excluded.append({
                "ticker": ticker, "stage": "liquidity",
                "reason": f"average daily dollar volume ${(adv or 0)/1e6:.1f}M below the "
                          f"${cfg['adv_dollar_floor']/1e6:.0f}M floor",
            })
            continue

        rows.append({
            "ticker": ticker,
            "listing": listing,
            "price": price,
            "values": fund["values"],
            "missing": dict(fund["missing"]),
            "provenance": fund["provenance"],
            "notes": fund["notes"],
            "revenue_ttm": fund["revenue_ttm"],
        })

    funnel.append({"stage": "has EDGAR fundamentals", "count": len(universe["listings"]) - stage_counts["no_fundamentals"]})
    funnel.append({"stage": "has an adjusted close", "count": len(universe["listings"]) - stage_counts["no_fundamentals"] - stage_counts["no_price"]})
    funnel.append({"stage": "files 10-K/10-Q (foreign private issuers removed)", "count": len(universe["listings"]) - sum([stage_counts["no_fundamentals"], stage_counts["no_price"], stage_counts["foreign_filer"]])})
    funnel.append({"stage": f"at least {cfg['min_quarters_filed']} periodic filings", "count": len(rows) + stage_counts["illiquid"]})
    funnel.append({"stage": f"average daily dollar volume >= ${cfg['adv_dollar_floor']/1e6:.0f}M", "count": len(rows)})
    return rows


def public_row(row: dict) -> dict:
    """The free tier: the ranked list, without the differentiated asset."""
    return {
        "ticker": row["ticker"],
        "name": row["name"],
        "sector": row["sector"],
        "exchange": row["exchange"],
        "market_cap": row["market_cap"],
        "price": row["price"],
        "price_change_pct": row["price_change_pct"],
        "composite": row["composite"],
        "rank": row["rank"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--force-history", action="store_true",
                        help="overwrite this month's history file (normally refused)")
    parser.add_argument("--no-history", action="store_true",
                        help="refresh the display payloads without touching data/history/ "
                             "(used by the weekly price refresh)")
    args = parser.parse_args()

    ensure_dirs()
    settings = load_settings()
    weights_cfg = load_weights()
    weights = weights_cfg["weights"]
    scoring_cfg = settings["scoring"]

    universe = read_json(DATA_DIR / "universe.json")
    fundamentals = read_json(DATA_DIR / "fundamentals.json")
    prices = read_json(DATA_DIR / "price_snapshot.json")
    if not (universe and fundamentals and prices):
        print("missing an input file - run fetch_universe, fetch_prices and fetch_fundamentals first",
              file=sys.stderr)
        return 1

    scoring_date = date.fromisoformat(args.as_of or prices["scoring_date"])
    run_date = date.today()
    prior_scoring_date = last_day_of_prior_month(scoring_date.replace(day=1))

    funnel = list(universe["funnel"])
    excluded: list[dict] = []
    rows = build_rows(universe, fundamentals, prices, settings, funnel, excluded)

    # ---- model validity: three separate tables, never ranked against each other
    segmented: dict[str, list[dict]] = {k: [] for k in SEGMENTS}
    for row in rows:
        row["segment"] = classify_segment(row["listing"], row["revenue_ttm"])
        segmented[row["segment"]].append(row)
    for key, label in SEGMENTS.items():
        funnel.append({"stage": f"segment: {label}", "count": len(segmented[key])})

    results = {}
    insufficient: list[dict] = []
    for key, group in segmented.items():
        if not group:
            results[key] = {"scored": [], "insufficient": [], "metric_resolution": {},
                            "applicable_metrics": [], "cohorts": {}}
            continue
        results[key] = score_segment(
            group,
            weights=weights,
            winsor=(scoring_cfg["winsorize_lo_pct"], scoring_cfg["winsorize_hi_pct"]),
            roic_hurdle=scoring_cfg["roic_hurdle"],
            min_cohort=settings["universe"]["min_sector_cohort"],
            coverage_threshold=settings["universe"]["coverage_threshold"],
            metric_applicability=settings["universe"].get("segment_metric_applicability", 0.40),
        )
        rank_stability(results[key]["scored"], scoring_cfg["stability_sweep"])
        insufficient.extend(results[key]["insufficient"])

    funnel.append({"stage": f"coverage >= {settings['universe']['coverage_threshold']:.0%} of applicable metrics",
                   "count": sum(len(r["scored"]) for r in results.values())})

    # ---- month-over-month, against the previous run's stored record
    prior = read_json(HISTORY_DIR / f"scores_{month_key(prior_scoring_date)}.json")
    prior_by_ticker = {}
    if prior:
        for seg in prior.get("segments", {}).values():
            for r in seg:
                prior_by_ticker[r["ticker"]] = r

    def emit(row: dict) -> dict:
        listing, price = row["listing"], row["price"]
        was = prior_by_ticker.get(row["ticker"])
        composite = row.get("composite")
        out = {
            "ticker": row["ticker"],
            "name": listing["name"],
            "sector": listing["sector"],
            "industry": listing["industry"],
            "exchange": listing["exchange"],
            "cik": listing["cik"],
            "market_cap": listing["market_cap"],
            "segment": row["segment"],
            "scoring_date": scoring_date.isoformat(),
            "run_date": run_date.isoformat(),
            # Price at the scoring date and the prior scoring date, BOTH read from
            # today's adjusted series - see the module docstring.
            "price": price["price"],
            "price_at_scoring_asof": price["price_date"],
            "prior_price": price["prior_price"],
            "prior_price_date": price["prior_price_date"],
            "price_change_pct": price["change_pct"],
            "price_change_abs": price["change_abs"],
            "composite": composite,
            "rank": row.get("rank"),
            "sector_decile": row.get("sector_decile"),
            "sector_rank": row.get("sector_rank"),
            "factors": row["factors"],
            "metrics": {
                key: {
                    "raw": row["values"].get(key),
                    "pct": row["percentiles"].get(key),
                    "basis": row["bases"].get(key),
                }
                for key in row["applicable_metrics"]
            },
            "missing": sorted(row["missing"].keys()),
            "missing_reasons": row["missing"],
            "coverage": row["coverage"],
            "stability": row.get("stability"),
            "fundamentals_asof": row["provenance"]["fundamentals_asof"],
            "filed": row["provenance"]["filed"],
            "accn": row["provenance"]["accn"],
            "form": row["provenance"]["form"],
            # Only the derivation trail: the period, filing date, accession and
            # form are already flattened above, and two copies of one field are
            # two things that can drift apart. Stale inputs are listed once, in
            # the coverage report, rather than in every row of every payload.
            "derivation": {
                k: v for k, v in row["provenance"].items()
                if k not in ("fundamentals_asof", "filed", "accn", "form", "stale_inputs", "unmapped_candidates")
            },
            "notes": row["notes"],
            "weights_version": weights_cfg["version"],
            "is_new": was is None,
            "composite_change": (
                round(composite - was["composite"], 2)
                if was and was.get("composite") is not None and composite is not None else None
            ),
            # A rank that improves is a positive number, matching the arrow in the UI.
            "rank_change": (
                was["rank"] - row["rank"]
                if was and was.get("rank") is not None and row.get("rank") is not None else None
            ),
        }
        return out

    segments_out = {key: [emit(r) for r in results[key]["scored"]] for key in SEGMENTS}
    insufficient_out = [
        {
            "ticker": r["ticker"], "name": r["listing"]["name"], "sector": r["listing"]["sector"],
            "exchange": r["listing"]["exchange"], "market_cap": r["listing"]["market_cap"],
            "segment": r["segment"], "coverage": r["coverage"],
            "reason": r["insufficient_reason"], "missing": sorted(r["missing"].keys()),
            "missing_reasons": r["missing"],
            "price": r["price"]["price"], "price_change_pct": r["price"]["change_pct"],
        }
        for r in insufficient
    ]

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scoring_date": scoring_date.isoformat(),
        "prior_scoring_date": prior_scoring_date.isoformat(),
        "run_date": run_date.isoformat(),
        "weights_version": weights_cfg["version"],
        "weights": weights,
        "first_run": prior is None,
        "settings": {"scoring": scoring_cfg, "universe": settings["universe"]},
        "sources": {
            "fundamentals": {"name": fundamentals["source"], "licence": fundamentals["source_licence"]},
            "prices": {"name": prices["provider"], "licence": prices["provider_licence"]},
            "universe": {"name": universe["source"], "licence": "no redistribution grant"},
        },
        "counts": {key: len(v) for key, v in segments_out.items()} | {"insufficient": len(insufficient_out)},
    }

    full = {
        "meta": meta,
        "segments_meta": [
            {"key": k, "label": v,
             "applicable_metrics": results[k]["applicable_metrics"],
             "metric_resolution": results[k]["metric_resolution"],
             "cohorts": results[k]["cohorts"]}
            for k, v in SEGMENTS.items()
        ],
        "metrics": METRICS,
        "factors": FACTORS,
        "segments": segments_out,
        "insufficient": insufficient_out,
    }
    write_json(DATA_DIR / "scores_full.json", full, compact=True)

    public = {
        "meta": {k: meta[k] for k in ("generated_at", "scoring_date", "run_date", "weights_version", "counts")},
        "note": "Free tier: ranked list only. Factor scores, sub-metric percentiles and history "
                "are in scores_full.json.",
        "segments": {k: [public_row(r) for r in v] for k, v in segments_out.items()},
    }
    write_json(DATA_DIR / "scores_public.json", public, compact=True)

    # ---- append-only history
    history_path = HISTORY_DIR / f"scores_{month_key(scoring_date)}.json"
    if args.no_history:
        # The weekly price refresh must never create a month's record. If it
        # fired before that month's scoring run - possible whenever the 1st
        # falls on a Saturday - it would write a record built on fresh prices
        # and stale fundamentals, and append-only means the real run could
        # never correct it.
        print(f"  history untouched (--no-history); {month_key(scoring_date)} left to the scoring run")
    elif history_path.exists() and not args.force_history:
        print(f"  history for {month_key(scoring_date)} already exists - left untouched (append-only)")
    else:
        write_json(history_path, {
            "meta": meta,
            "backtested": False,
            "segments": segments_out,
        }, compact=True)
        print(f"  history -> {history_path}")

    rebuild_history_index()

    coverage = {
        "generated_at": meta["generated_at"],
        "scoring_date": meta["scoring_date"],
        "funnel": funnel,
        "metric_resolution_by_segment": {
            k: results[k]["metric_resolution"] for k in SEGMENTS
        },
        "applicable_metrics_by_segment": {k: results[k]["applicable_metrics"] for k in SEGMENTS},
        "excluded": excluded,
        "insufficient_data": insufficient_out,
        "unresolved_metrics": [
            {"ticker": r["ticker"], "metric": key, "reason": reason}
            for seg in segments_out.values() for r in seg
            for key, reason in r["missing_reasons"].items()
        ],
        # Figures rejected because they came from a tag the company abandoned
        # (older than max_input_age_days before its latest balance sheet).
        "stale_inputs_ignored": [
            {"ticker": r["ticker"], **s}
            for r in rows for s in r["provenance"].get("stale_inputs", [])
        ],
        "price_review": prices.get("review", []),
        "price_failures": prices.get("failures", []),
        "fundamentals_failures": fundamentals.get("failures", []),
    }
    write_json(DATA_DIR / "coverage_report.json", coverage, compact=True)

    # ---- month-over-month drift, gated in the workflow by check_drift.py
    drift = build_drift_report(
        scoring_date=scoring_date,
        prior_scoring_date=prior_scoring_date,
        scored_rows=[r for seg in segments_out.values() for r in seg],
        prior_rows=[r for seg in prior["segments"].values() for r in seg] if prior else None,
        eligible_rows=rows,
        insufficient_rows=insufficient_out,
        thresholds=settings["drift"],
    )
    write_json(DATA_DIR / "drift_report.json", drift)
    print(f"  drift vs {month_key(prior_scoring_date)}: {drift['status']}")

    print(f"scores -> data/scores_full.json + data/scores_public.json")
    for stage in funnel:
        print(f"  {stage['count']:>6}  {stage['stage']}")
    print(f"  {len(insufficient_out):>6}  routed to 'Insufficient data'")
    total_metrics = sum(len(r["metrics"]) for seg in segments_out.values() for r in seg)
    resolved_metrics = sum(
        1 for seg in segments_out.values() for r in seg for m in r["metrics"].values() if m["pct"] is not None
    )
    print(f"\n  metric coverage across scored stocks: {resolved_metrics}/{total_metrics} "
          f"({resolved_metrics / max(total_metrics, 1):.0%})")
    return 0


def rebuild_history_index() -> None:
    """ticker -> [{month, composite, rank}] for the sparkline column.

    Rebuilt from the append-only monthly files rather than accumulated in place,
    so it can never drift from them.
    """
    index: dict[str, list[dict]] = {}
    months: list[str] = []
    for path in sorted(HISTORY_DIR.glob("scores_*.json")):
        month = path.stem.replace("scores_", "")
        payload = read_json(path) or {}
        months.append(month)
        for seg in payload.get("segments", {}).values():
            for row in seg:
                index.setdefault(row["ticker"], []).append({
                    "month": month,
                    "composite": row.get("composite"),
                    "rank": row.get("rank"),
                    "price": row.get("price"),
                    # Factor scores travel with the index so the score-versus-price
                    # view can report per factor, not only on the composite.
                    "factors": row.get("factors"),
                    "sector": row.get("sector"),
                    "weights_version": row.get("weights_version"),
                    "backtested": payload.get("backtested", False),
                })
    for series in index.values():
        series.sort(key=lambda r: r["month"])
    write_json(DATA_DIR / "history_index.json", {
        "months": sorted(months),
        "observations": len(months),
        "tickers": index,
    }, compact=True)


if __name__ == "__main__":
    raise SystemExit(main())
