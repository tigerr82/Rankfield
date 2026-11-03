from rankfield.adjusted import adjusted_prices


def _rec(rows):
    return {"segments": {"operating": [{"ticker": t, "price": p, "prior_price": q} for t, p, q in rows]}}


def test_a_split_between_two_months_does_not_show_as_a_collapse():
    records = {
        "2026-08": _rec([("AAA", 100.0, None)]),
        "2026-09": _rec([("AAA", 98.0, 100.0)]),
        "2026-10": _rec([("AAA", 15.0, 14.7)]),   # 6.67-for-1: September re-read as 14.70
    }
    adj = adjusted_prices(records)
    assert adj["2026-10"]["AAA"] == 15.0
    assert adj["2026-09"]["AAA"] == 14.7
    assert round(adj["2026-08"]["AAA"], 2) == 15.0


def test_restated_latest_prices_catch_a_split_after_the_monthly_run():
    records = {"2026-09": _rec([("AAA", 100.0, None)]), "2026-10": _rec([("AAA", 110.0, 100.0)])}
    latest = {"AAA": {"price": 55.0, "prior_price": 50.0}}
    adj = adjusted_prices(records, latest)
    assert adj["2026-10"]["AAA"] == 55.0
    assert adj["2026-09"]["AAA"] == 50.0


def test_a_gap_or_a_missing_prior_price_leaves_earlier_months_empty_not_guessed():
    records = {
        "2026-08": _rec([("AAA", 100.0, None), ("BBB", 10.0, None)]),
        "2026-09": _rec([("BBB", 10.0, None)]),
        "2026-10": _rec([("AAA", 20.0, 19.0), ("BBB", 11.0, None)]),
    }
    adj = adjusted_prices(records)
    assert adj["2026-08"]["AAA"] is None
    assert adj["2026-10"]["AAA"] == 20.0
    assert adj["2026-08"]["BBB"] is None and adj["2026-09"]["BBB"] is None
    assert adj["2026-10"]["BBB"] == 11.0


def test_a_company_that_left_keeps_its_own_basis():
    records = {"2026-09": _rec([("AAA", 50.0, None)]), "2026-10": _rec([("BBB", 5.0, None)])}
    assert adjusted_prices(records)["2026-09"]["AAA"] == 50.0
