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


# ---- hysteresis: easy to stay, hard to join

def volume_run(adv, was_scored, ratio=0.8):
    settings = {"universe": {**SETTINGS["universe"], "adv_retention_ratio": ratio}}
    universe = {"listings": [{"ticker": "XYZ", "cik": "1"}]}
    prices = {"prices": {"XYZ": {"adv_dollar": adv}}}
    excluded = []
    rows = build_rows(universe, fundamentals("2026-06-30"), prices, settings, [], excluded,
                      prior_scored={"XYZ"} if was_scored else frozenset())
    return rows, excluded


def test_a_ranked_company_just_under_the_volume_floor_stays():
    rows, excluded = volume_run(4_960_000, was_scored=True)   # OPKO: $4.96M vs $5M
    assert [r["ticker"] for r in rows] == ["XYZ"] and excluded == []


def test_a_company_not_yet_ranked_must_clear_the_full_floor():
    rows, excluded = volume_run(4_960_000, was_scored=False)
    assert rows == [] and "liquidity" in excluded[0]["stage"]


def test_a_ranked_company_well_under_the_floor_still_leaves():
    rows, _ = volume_run(3_500_000, was_scored=True)          # below 80% of $5M
    assert rows == []


def test_a_failed_download_is_not_reported_as_missing_filings():
    universe = {"listings": [{"ticker": "XYZ", "cik": "1"}]}
    fund = {"as_of": "2026-08-31", "companies": {},
            "failures": [{"ticker": "XYZ", "reason": "fetch failed: Compressed file ended"}]}
    excluded = []
    build_rows(universe, fund, {"prices": {}}, SETTINGS, [], excluded)
    assert "fetch failed" in excluded[0]["reason"]


# ---- a company the SEC's structured data has fallen behind on is not a company that stopped reporting

LAG = {"form": "10-Q", "filed": "2026-07-29", "report_date": "2026-06-30"}


def lag_run(latest, *, was_scored, newer, carry_days=300):
    settings = {"universe": {**SETTINGS["universe"], "carry_report_age_days": carry_days}}
    fund = fundamentals(latest)
    fund["as_of"] = "2026-10-31"
    fund["companies"]["XYZ"]["newer_filing"] = newer
    universe = {"listings": [{"ticker": "XYZ", "cik": "1"}]}
    prices = {"prices": {"XYZ": {"adv_dollar": 1e9}}}
    excluded, carried = [], []
    rows = build_rows(universe, fund, prices, settings, [], excluded,
                      prior_scored={"XYZ"} if was_scored else frozenset(), carried=carried)
    return rows, excluded, carried


def test_a_ranked_company_with_a_newer_filing_the_data_lacks_stays_and_is_flagged():
    rows, excluded, carried = lag_run("2026-03-31", was_scored=True, newer=LAG)   # 214 days old
    assert [r["ticker"] for r in rows] == ["XYZ"] and excluded == []
    assert carried[0]["report_date"] == "2026-06-30"
    assert "SEC's filing index" in rows[0]["notes"][-1] and rows[0]["data_lag"] == LAG


def test_a_company_not_ranked_last_month_is_not_carried():
    rows, excluded, _ = lag_run("2026-03-31", was_scored=False, newer=LAG)
    assert rows == [] and "200 days" in excluded[0]["reason"]


def test_a_company_with_no_newer_filing_on_record_is_still_stale():
    rows, _, _ = lag_run("2026-03-31", was_scored=True, newer=None)
    assert rows == []


def test_the_carry_has_a_limit():
    rows, _, _ = lag_run("2025-12-31", was_scored=True, newer=LAG)               # 304 days old
    assert rows == []
