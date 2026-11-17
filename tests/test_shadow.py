from datetime import date

from rankfield.facts import FactSet
from rankfield.shadow import shadow_metrics

AS_OF = date(2026, 9, 30)


def _duration(start, end, val, filed, form="10-K"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "accn": "a"}


def _instant(end, val, filed, form="10-K"):
    return {"end": end, "val": val, "filed": filed, "form": form, "accn": "a"}


def _fs(**lines):
    facts = {}
    for concept, rows in lines.items():
        facts[concept] = {"units": {"USD": rows}}
    return FactSet({"entityName": "T", "facts": {"us-gaap": facts}}, AS_OF)


YEAR = ("2025-07-01", "2026-06-30")
FILED = "2026-08-15"


def _base(**extra):
    lines = {
        "NetIncomeLoss": [_duration(*YEAR, 100.0, FILED)],
        "NetCashProvidedByUsedInOperatingActivities": [_duration(*YEAR, 160.0, FILED)],
        "Assets": [_instant("2025-06-30", 1000.0, "2025-08-15"), _instant("2026-06-30", 1200.0, FILED)],
    }
    lines.update(extra)
    return _fs(**lines)


def test_accruals_are_income_less_cash_flow_over_average_assets():
    out = shadow_metrics(_base(), 2000.0)
    assert round(out["values"]["accruals"], 4) == round((100 - 160) / 1100, 4)


def test_net_payout_is_repurchases_less_issuance_over_market_cap():
    fs = _base(
        PaymentsForRepurchaseOfCommonStock=[_duration(*YEAR, 80.0, FILED)],
        ProceedsFromIssuanceOfCommonStock=[_duration(*YEAR, 20.0, FILED)],
    )
    assert shadow_metrics(fs, 2000.0)["values"]["net_payout_yield"] == 0.03


def test_a_company_that_raised_equity_shows_a_negative_yield():
    fs = _base(ProceedsFromIssuanceOfCommonStock=[_duration(*YEAR, 200.0, FILED)])
    assert shadow_metrics(fs, 2000.0)["values"]["net_payout_yield"] == -0.1


def test_neither_line_tagged_is_none_issued_and_is_said_so():
    out = shadow_metrics(_base(), 2000.0)
    assert out["values"]["net_payout_yield"] == 0.0
    assert "treated as none" in out["sources"]["net_payout_yield"]


def test_nothing_is_invented_without_a_market_cap_or_a_cash_flow_statement():
    assert shadow_metrics(_base(), None)["values"]["net_payout_yield"] is None
    bare = _fs(Assets=[_instant("2026-06-30", 1200.0, FILED)])
    out = shadow_metrics(bare, 2000.0)
    assert out["values"] == {"net_payout_yield": None, "accruals": None}
    assert out["sources"]["accruals"]
