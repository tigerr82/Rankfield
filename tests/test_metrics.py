"""The formula appendix and its edge-case table.

Every case here exists because the alternative is a number that looks like a
judgement without being one: a negative multiple ranking as "cheap", a
negative-equity company scoring well on leverage, a missing input becoming a
zero that silently punishes the company.
"""
from datetime import date

import pytest

from rankfield.facts import FactSet
from rankfield.metrics import METRIC_KEYS, compute_metrics, total_debt

AS_OF = date(2026, 8, 31)


def build(**overrides):
    """A complete, ordinary operating company, with fields overridable."""
    base = {
        "Revenues": 1000.0, "CostOfGoodsAndServicesSold": 600.0,
        "OperatingIncomeLoss": 200.0, "DepreciationDepletionAndAmortization": 50.0,
        "NetCashProvidedByUsedInOperatingActivities": 180.0,
        "PaymentsToAcquirePropertyPlantAndEquipment": 60.0,
        "IncomeTaxExpenseBenefit": 40.0,
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": 180.0,
        "NetIncomeLoss": 140.0,
        "Assets": 2000.0, "AssetsCurrent": 800.0, "Liabilities": 1200.0,
        "LiabilitiesCurrent": 400.0, "StockholdersEquity": 800.0,
        "RetainedEarningsAccumulatedDeficit": 300.0,
        "CashAndCashEquivalentsAtCarryingValue": 150.0,
        "LongTermDebtNoncurrent": 400.0,
    }
    base.update(overrides)

    duration = {
        "Revenues", "CostOfGoodsAndServicesSold", "OperatingIncomeLoss",
        "DepreciationDepletionAndAmortization",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment", "IncomeTaxExpenseBenefit",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "NetIncomeLoss",
    }
    gaap = {}
    for concept, value in base.items():
        if value is None:
            continue
        rows = []
        if concept in duration:
            # six fiscal years, so five-year metrics resolve
            for year in range(2020, 2026):
                rows.append({
                    "start": f"{year}-01-01", "end": f"{year}-12-31",
                    "val": value * (1 + 0.05 * (year - 2025)),
                    "filed": f"{year + 1}-02-15", "form": "10-K", "accn": f"a{year}",
                })
        else:
            for year in range(2020, 2026):
                rows.append({
                    "end": f"{year}-12-31", "val": value * (1 + 0.05 * (year - 2025)),
                    "filed": f"{year + 1}-02-15", "form": "10-K", "accn": f"a{year}",
                })
        gaap[concept] = {"units": {"USD": rows}}
    return FactSet({"entityName": "Test Co", "facts": {"us-gaap": gaap}}, AS_OF)


def run(market_cap=5000.0, **overrides):
    return compute_metrics(build(**overrides), market_cap=market_cap)


class TestHealthyBaseline:
    def test_a_complete_company_resolves_every_metric(self):
        result = run()
        unresolved = [k for k in METRIC_KEYS if result["values"][k] is None]
        assert unresolved == [], f"unexpectedly missing: {unresolved} ({result['missing']})"

    def test_values_are_in_plausible_ranges(self):
        v = run()["values"]
        assert 0 < v["roic"] < 1
        assert v["gpoa"] == pytest.approx(0.2, abs=0.01)     # (1000-600)/2000
        assert v["debt_equity"] == pytest.approx(0.5, abs=0.01)  # 400/800
        assert v["ebit_ev"] > 0

    def test_provenance_is_recorded_for_audit(self):
        prov = run()["provenance"]
        assert prov["fundamentals_asof"]
        assert prov["filed"]
        assert prov["accn"]
        assert prov["form"]


class TestEdgeCaseTable:
    def test_negative_equity_nulls_debt_to_equity_rather_than_producing_a_large_negative(self):
        result = run(StockholdersEquity=-500.0)
        assert result["values"]["debt_equity"] is None
        assert "negative" in result["missing"]["debt_equity"]

    def test_negative_ebitda_nulls_net_debt_to_ebitda(self):
        # A negative multiple must never rank as cheap.
        result = run(OperatingIncomeLoss=-300.0, DepreciationDepletionAndAmortization=50.0)
        assert result["values"]["net_debt_ebitda"] is None
        assert "negative" in result["missing"]["net_debt_ebitda"]

    def test_zero_ebitda_nulls_net_debt_to_ebitda(self):
        result = run(OperatingIncomeLoss=-50.0, DepreciationDepletionAndAmortization=50.0)
        assert result["values"]["net_debt_ebitda"] is None

    def test_negative_enterprise_value_nulls_every_value_metric(self):
        # Cash far exceeding market cap plus debt.
        result = run(market_cap=100.0, CashAndCashEquivalentsAtCarryingValue=5000.0)
        for key in ("ebit_ev", "ebitda_ev", "fcf_ev"):
            assert result["values"][key] is None
            assert "negative enterprise value" in result["missing"][key]

    def test_a_true_negative_ebit_is_kept_not_nulled(self):
        # Genuinely poor, and ranked accordingly - not excluded.
        result = run(OperatingIncomeLoss=-100.0)
        assert result["values"]["ebit_ev"] is not None
        assert result["values"]["ebit_ev"] < 0

    def test_zero_assets_nulls_gpoa_rather_than_dividing_by_zero(self):
        result = run(Assets=0.0)
        assert result["values"]["gpoa"] is None

    def test_fewer_than_five_years_nulls_earnings_variability(self):
        fs = build()
        # Strip the net income history down to three years.
        rows = fs._facts["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
        fs._facts["us-gaap"]["NetIncomeLoss"]["units"]["USD"] = rows[-3:]
        fs._cache.clear()
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["values"]["earn_var"] is None
        assert "fewer than 5" in result["missing"]["earn_var"]

    def test_missing_metrics_are_never_silently_zero(self):
        result = run(StockholdersEquity=-500.0, OperatingIncomeLoss=-300.0)
        for key, value in result["values"].items():
            if value is None:
                assert key in result["missing"], f"{key} is null with no recorded reason"

    def test_every_unresolved_metric_carries_a_human_reason(self):
        result = run(Assets=None, StockholdersEquity=None, Liabilities=None)
        for key, reason in result["missing"].items():
            assert reason and reason.strip(), f"{key} has an empty reason"
            assert not reason.endswith(" "), f"{key} reason is truncated: {reason!r}"


class TestTotalDebt:
    def test_a_combined_tag_is_used_directly(self):
        fs = build(LongTermDebtNoncurrent=None)
        fs._facts["us-gaap"]["DebtLongtermAndShorttermCombinedAmount"] = {
            "units": {"USD": [{"end": "2025-12-31", "val": 777.0, "filed": "2026-02-15",
                               "form": "10-K", "accn": "a"}]}}
        fs._cache.clear()
        value, how = total_debt(fs)
        assert value == 777.0
        assert how == "combined-tag"

    def test_components_are_summed_when_no_combined_tag_exists(self):
        value, how = total_debt(build())
        assert value == 400.0
        assert how == "noncurrent+current+short"

    def test_unresolvable_debt_is_reported_as_such(self):
        value, how = total_debt(build(LongTermDebtNoncurrent=None))
        assert value is None
        assert how == "unresolved"

    def test_unresolvable_debt_nulls_the_dependent_metrics(self):
        result = run(LongTermDebtNoncurrent=None)
        assert result["values"]["debt_equity"] is None
        assert result["values"]["net_debt_ebitda"] is None
        assert result["values"]["roic"] is None


class TestMissingMarketCap:
    def test_no_market_cap_nulls_the_value_metrics_with_an_accurate_reason(self):
        result = run(market_cap=None)
        for key in ("ebit_ev", "ebitda_ev", "fcf_ev"):
            assert result["values"][key] is None
            # The reason must name the real cause, not blame total debt.
            assert "market cap" in result["missing"][key].lower()


class TestTaxRate:
    def test_a_reported_rate_is_used_and_clamped(self):
        prov = run()["provenance"]
        assert prov["tax_rate_source"] == "reported"
        assert 0.0 <= prov["effective_tax_rate"] <= 0.35

    def test_an_extreme_rate_is_clamped_to_the_ceiling(self):
        prov = run(IncomeTaxExpenseBenefit=500.0)["provenance"]
        assert prov["effective_tax_rate"] == 0.35

    def test_a_loss_making_period_falls_back_to_the_statutory_rate(self):
        prov = run(
            IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest=-100.0
        )["provenance"]
        assert prov["tax_rate_source"] == "statutory-fallback"
        assert prov["effective_tax_rate"] == 0.21


class TestDeltaGpoaIsLikeForLike:
    """dGPOA must compare two fiscal years, not a trailing figure against one.

    Dividing the near endpoint by the latest quarter-end balance sheet while the
    far endpoint used a fiscal year-end one made the result depend on how far a
    company's fiscal year-end sat from the scoring date. A December filer scored
    in August was measured against a balance sheet six months newer than its own
    historical endpoint, so growing the asset base was punished for the calendar.
    """

    def test_a_growing_asset_base_is_not_punished_for_the_calendar(self):
        fs = build()
        gaap = fs._facts["us-gaap"]
        # Assets jump 50% in the stub quarter after the last fiscal year end -
        # exactly the shape of a capital-expenditure surge.
        gaap["Assets"]["units"]["USD"].append(
            {"end": "2026-06-30", "val": 3000.0, "filed": "2026-07-30", "form": "10-Q", "accn": "q"}
        )
        # A quarter, which is what filers actually tag - not a 12-month window,
        # which would legitimately read as a new fiscal year.
        for concept in ("Revenues", "CostOfGoodsAndServicesSold"):
            rows = gaap[concept]["units"]["USD"]
            quarter = rows[-1]["val"] / 4
            for start, end in (("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-30")):
                rows.append({"start": start, "end": end, "val": quarter,
                             "filed": "2026-07-30", "form": "10-Q", "accn": "q"})
        fs._cache.clear()
        result = compute_metrics(fs, market_cap=5000.0)
        delta = result["values"]["delta_gpoa"]
        assert delta is not None
        # The fiscal-year ratio barely moved, so dGPOA must stay near zero
        # rather than collapsing because of the newer, larger balance sheet.
        assert abs(delta) < 0.05, f"dGPOA {delta:+.3f} reflects the balance-sheet date, not the business"

    def test_both_endpoints_come_from_the_annual_series(self):
        fs = build()
        from rankfield.metrics import _annual_gpoa
        result = compute_metrics(fs, market_cap=5000.0)
        expected = _annual_gpoa(fs, 0) - _annual_gpoa(fs, 3)
        assert result["values"]["delta_gpoa"] == pytest.approx(expected)


class TestAbandonedTags:
    """A tag the filer stopped using must never supply a current figure.

    The real cases: Microsoft's debt from a 2015 combined tag, Johnson & Johnson's
    operating income from 2015, Deere's 2026 revenue less its 2018 cost of goods.
    """

    @staticmethod
    def add(fs, concept, rows):
        fs._facts["us-gaap"][concept] = {"units": {"USD": rows}}
        fs._cache.clear()

    @staticmethod
    def annual(year, val):
        return {"start": f"{year}-01-01", "end": f"{year}-12-31", "val": val,
                "filed": f"{year + 1}-02-15", "form": "10-K", "accn": f"a{year}"}

    def test_a_stale_combined_debt_tag_falls_through_to_current_components(self):
        fs = build()
        self.add(fs, "DebtLongtermAndShorttermCombinedAmount",
                 [{"end": "2015-03-31", "val": 777.0, "filed": "2015-04-23", "form": "10-Q", "accn": "old"}])
        value, how = total_debt(fs)
        assert value == 400.0
        assert how == "noncurrent+current+short"

    def test_stale_operating_income_is_not_used_as_ebit(self):
        fs = build(OperatingIncomeLoss=None)
        self.add(fs, "OperatingIncomeLoss", [self.annual(2014, 9999.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["ebit_source"] == "unresolved"
        assert result["values"]["ebit_ev"] is None
        assert {"concept": "OperatingIncomeLoss", "last_reported": "2014-12-31"} in result["provenance"]["stale_inputs"]
        assert any("OperatingIncomeLoss" in note for note in result["notes"])

    def test_stale_operating_income_falls_back_to_a_current_derivation(self):
        fs = build(OperatingIncomeLoss=None)
        self.add(fs, "OperatingIncomeLoss", [self.annual(2014, 9999.0)])
        self.add(fs, "OperatingExpenses", [self.annual(2025, 200.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["ebit_source"] == "derived: Rev - COGS - OpEx"
        assert result["raw_inputs"]["ebit"] == pytest.approx(1000.0 - 600.0 - 200.0)

    def test_current_revenue_is_never_netted_against_stale_cost_of_goods(self):
        fs = build(CostOfGoodsAndServicesSold=None)
        self.add(fs, "CostOfGoodsAndServicesSold", [self.annual(2018, 100.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["values"]["gpoa"] is None
        assert result["provenance"]["gross_profit_source"] == "unresolved"

    def test_a_company_with_only_current_tags_flags_nothing(self):
        result = run()
        assert result["provenance"]["stale_inputs"] == []
        assert result["provenance"]["unmapped_candidates"] == {}
        assert not any("no longer reports" in note for note in result["notes"])


class TestFallbackChains:
    """What replaces a figure once an abandoned tag no longer supplies it."""

    add = staticmethod(TestAbandonedTags.add)
    annual = staticmethod(TestAbandonedTags.annual)

    @staticmethod
    def instant(end, val):
        return {"end": end, "val": val, "filed": "2026-02-15", "form": "10-K", "accn": "x"}

    def test_no_operating_income_line_uses_pretax_income_plus_interest(self):
        # Johnson & Johnson, Lilly, Merck: straight from costs to pre-tax income.
        fs = build(OperatingIncomeLoss=None)
        self.add(fs, "InterestExpenseNonoperating", [self.annual(2025, 20.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["ebit_source"] == "derived: pretax income + interest expense"
        assert result["raw_inputs"]["ebit"] == pytest.approx(180.0 + 20.0)
        assert result["values"]["roic"] is not None

    def test_a_banks_deposit_interest_does_not_manufacture_ebit(self):
        fs = build(OperatingIncomeLoss=None)
        self.add(fs, "InterestExpenseOperating", [self.annual(2025, 900.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["ebit_source"] == "unresolved"

    def test_debt_moved_to_an_unsecured_notes_tag_is_found(self):
        fs = build(LongTermDebtNoncurrent=None)
        self.add(fs, "UnsecuredLongTermDebt", [self.instant("2025-12-31", 2481.0)])
        assert total_debt(fs) == (2481.0, "noncurrent+current+short")

    def test_a_company_whose_last_reported_debt_was_zero_has_no_debt(self):
        # Palantir: last debt tag, 2021, value zero; nothing since.
        fs = build(LongTermDebtNoncurrent=None)
        self.add(fs, "LongTermDebtNoncurrent", [self.instant("2021-12-31", 0.0)])
        assert total_debt(fs) == (0.0, "last-reported-zero")
        assert compute_metrics(fs, market_cap=5000.0)["values"]["debt_equity"] == 0.0

    def test_a_stale_non_zero_debt_is_not_assumed_to_be_zero(self):
        # Ford: last standard debt tag 2020, non-zero; its debt is elsewhere now.
        fs = build(LongTermDebtNoncurrent=None)
        self.add(fs, "LongTermDebtNoncurrent", [self.instant("2020-12-31", 291.0)])
        assert total_debt(fs) == (None, "unresolved")

    def test_an_unresolved_input_names_the_tags_the_company_reports_instead(self):
        fs = build(LongTermDebtNoncurrent=None)
        self.add(fs, "OtherLongTermDebtNoncurrent", [self.instant("2025-12-31", 350.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["raw_inputs"]["debt"] is None
        assert result["provenance"]["unmapped_candidates"] == {"debt": ["OtherLongTermDebtNoncurrent"]}

    def test_the_singular_service_spelling_of_cost_of_revenue_is_read(self):
        fs = build(CostOfGoodsAndServicesSold=None)
        self.add(fs, "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", [self.annual(2025, 600.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["values"]["gpoa"] == pytest.approx((1000.0 - 600.0) / 2000.0)
