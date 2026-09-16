"""The monthly drift gate: what it flags, what it ignores, and when it blocks."""
from datetime import date

from rankfield.drift import build_drift_report, render_issue

THRESHOLDS = {"warn_scored_drop_pct": 1, "block_scored_drop_pct": 5, "recently_abandoned_days": 450}
AUG, JUL = date(2026, 8, 31), date(2026, 7, 31)


def row(ticker, **pcts):
    return {"ticker": ticker, "metrics": {k: {"pct": v} for k, v in pcts.items()}, "missing_reasons": {}}


def universe(n, **pcts):
    return [row(f"T{i:03d}", **pcts) for i in range(n)]


def report(now, prior, eligible=(), insufficient=()):
    return build_drift_report(
        scoring_date=AUG, prior_scoring_date=JUL, scored_rows=list(now),
        prior_rows=None if prior is None else list(prior),
        eligible_rows=list(eligible), insufficient_rows=list(insufficient), thresholds=THRESHOLDS,
    )


def test_the_first_month_is_a_baseline_not_a_failure():
    assert report(universe(10, roic=50), None)["status"] == "baseline"


def test_an_unchanged_month_is_ok():
    assert report(universe(100, roic=50), universe(100, roic=50))["status"] == "ok"


def test_a_metric_lost_to_tagging_is_flagged_with_its_reason_and_candidates():
    now = universe(100, roic=50)
    now[0]["metrics"]["roic"]["pct"] = None
    now[0]["missing_reasons"]["roic"] = "EBIT, debt or equity unavailable"
    eligible = [{"ticker": "T000", "provenance": {"unmapped_candidates": {"debt": ["OtherLongTermDebtNoncurrent"]}}}]
    r = report(now, universe(100, roic=50), eligible)
    assert r["status"] == "warn"
    assert r["metrics_lost"] == [{"ticker": "T000", "metric": "roic", "reason": "EBIT, debt or equity unavailable",
                                  "candidates": {"debt": ["OtherLongTermDebtNoncurrent"]}}]
    assert "OtherLongTermDebtNoncurrent" in render_issue(r)


def test_a_metric_lost_to_the_companys_economics_is_not_drift():
    now = universe(100, net_debt_ebitda=50)
    now[0]["metrics"]["net_debt_ebitda"]["pct"] = None
    now[0]["missing_reasons"]["net_debt_ebitda"] = "EBITDA zero or negative"
    r = report(now, universe(100, net_debt_ebitda=50))
    assert r["status"] == "ok"
    assert r["metrics_lost"] == []
    assert len(r["metrics_lost_economic"]) == 1


def test_a_company_that_left_the_ranking_is_listed_with_the_reason():
    r = report(universe(99, roic=50), universe(100, roic=50),
               insufficient=[{"ticker": "T099", "reason": "resolved 5 of 11 applicable metrics"}])
    assert r["dropped_out"][0]["ticker"] == "T099"
    assert r["dropped_out"][0]["reason"] == "resolved 5 of 11 applicable metrics"
    assert r["status"] == "warn"


def test_a_collapse_of_the_scored_universe_blocks_publication():
    r = report(universe(90, roic=50), universe(100, roic=50))
    assert r["scored_change_pct"] == -10.0
    assert r["status"] == "block"
    assert "Publication was blocked" in render_issue(r)


def test_only_recently_abandoned_tags_are_reported():
    eligible = [{"ticker": "MSFT", "provenance": {"stale_inputs": [
        {"concept": "DebtLongtermAndShorttermCombinedAmount", "last_reported": "2015-03-31"},
        {"concept": "CommercialPaper", "last_reported": "2025-06-30"},
    ]}}]
    r = report(universe(10, roic=50), universe(10, roic=50), eligible)
    assert [e["concept"] for e in r["recently_abandoned_tags"]] == ["CommercialPaper"]
    assert r["status"] == "warn"
