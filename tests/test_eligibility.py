"""The eligibility funnel: who is scored at all."""
from compute_scores import build_rows

SETTINGS = {"universe": {"min_quarters_filed": 8, "max_report_age_days": 200, "adv_dollar_floor": 5_000_000}}


def fundamentals(latest_balance_sheet):
    return {"as_of": "2026-08-31", "companies": {"XYZ": {
        "files_domestic_forms": True, "forms": ["10-K", "10-Q"], "quarters_filed": 20,
        "values": {}, "missing": {}, "notes": [], "revenue_ttm": 1e9,
        "provenance": {"latest_balance_sheet": latest_balance_sheet},
    }}}


def run(latest):
    universe = {"listings": [{"ticker": "XYZ", "cik": "1"}]}
    prices = {"prices": {"XYZ": {"adv_dollar": 1e9}}}
    excluded = []
    rows = build_rows(universe, fundamentals(latest), prices, SETTINGS, [], excluded)
    return rows, excluded


def test_a_company_that_stopped_filing_is_not_scored_on_its_last_report():
    # Hub Group: latest report for the quarter to September 2025
    rows, excluded = run("2025-09-30")
    assert rows == []
    assert "2025-09-30" in excluded[0]["reason"]


def test_a_current_filer_is_scored():
    rows, excluded = run("2026-06-30")
    assert [r["ticker"] for r in rows] == ["XYZ"]
    assert excluded == []
