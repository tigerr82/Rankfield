"""The formula appendix and its edge-case table.

Every case here exists because the alternative is a number that looks like a
judgement without being one: a negative multiple ranking as "cheap", a
negative-equity company scoring well on leverage, a missing input becoming a
zero that silently punishes the company.
"""
from datetime import date

import pytest

from rankfield.facts import FactSet
from rankfield.metrics import (
    METRIC_KEYS,
    _ebit,
    compute_metrics,
    normalised_ebit,
    revenue_latest_year_change,
    revenue_trend,
    total_debt,
)

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
        # The fixture files annual reports only; the operating-income change needs
        # quarters and is covered by TestOperatingIncomeChange.
        result = run()
        unresolved = [k for k in METRIC_KEYS if result["values"][k] is None and k != "op_inc_change"]
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
        # a borrowing the company clearly has - its notes are in the footnotes -
        # but under no tag we read: unresolved, never guessed
        fs = build(LongTermDebtNoncurrent=None)
        fs._facts["us-gaap"]["NotesPayableToFormerParent"] = {
            "units": {"USD": [{"end": "2025-12-31", "val": 350.0, "filed": "2026-02-15",
                               "form": "10-K", "accn": "a"}]}}
        fs._cache.clear()
        value, how = total_debt(fs)
        assert value is None
        assert how == "unresolved"

    def test_unresolvable_debt_nulls_the_dependent_metrics(self):
        fs = build(LongTermDebtNoncurrent=None)
        fs._facts["us-gaap"]["NotesPayableToFormerParent"] = {
            "units": {"USD": [{"end": "2025-12-31", "val": 350.0, "filed": "2026-02-15",
                               "form": "10-K", "accn": "a"}]}}
        fs._cache.clear()
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["values"]["debt_equity"] is None
        assert result["values"]["net_debt_ebitda"] is None
        assert result["values"]["roic"] is None

    def test_a_company_that_never_filed_a_borrowing_has_no_debt(self):
        # 1.8: Intuitive Surgical, Reddit, a clinical-stage biotech - equity-funded,
        # not silent. Absent debt is zero only when the history holds nothing debt-like.
        value, how = total_debt(build(LongTermDebtNoncurrent=None))
        assert (value, how) == (0.0, "no debt tag ever filed")
        result = run(LongTermDebtNoncurrent=None)
        assert result["values"]["debt_equity"] == 0.0
        assert result["values"]["roic"] is not None

    def test_an_unused_credit_facility_is_not_a_borrowing(self):
        # Reddit files only the commitment fee on an undrawn revolver
        fs = build(LongTermDebtNoncurrent=None)
        fs._facts["us-gaap"]["LineOfCreditFacilityUnusedCapacityCommitmentFeePercentage"] = {
            "units": {"pure": [{"end": "2025-12-31", "val": 0.002, "filed": "2026-02-15",
                                "form": "10-K", "accn": "a"}]}}
        fs._cache.clear()
        assert total_debt(fs) == (0.0, "no debt tag ever filed")

    def test_one_slice_of_a_filers_debt_is_not_read_as_all_of_it(self):
        # CubeSmart tags $98M of notes and loans payable against some $3B of real
        # debt; Ameriprise reports a revolver at zero while its senior notes sit
        # in a tag we do not read. Neither may produce a number, and neither may
        # pass for debt-free.
        for tag, value in (("NotesAndLoansPayable", 98.0), ("LineOfCredit", 0.0),
                           ("OtherBorrowings", 114.0), ("JuniorSubordinatedNotes", 2059.0)):
            fs = build(LongTermDebtNoncurrent=None)
            fs._facts["us-gaap"][tag] = {
                "units": {"USD": [{"end": "2025-12-31", "val": value, "filed": "2026-02-15",
                                   "form": "10-K", "accn": "a"}]}}
            fs._cache.clear()
            assert total_debt(fs) == (None, "unresolved"), f"{tag} was read as debt"

    def test_a_convertible_note_a_software_filer_tags_alone_is_read(self):
        # Datadog, DoorDash, HubSpot: $986M of converts under a tag no general
        # debt list reached before 1.8
        fs = build(LongTermDebtNoncurrent=None)
        fs._facts["us-gaap"]["ConvertibleLongTermNotesPayable"] = {
            "units": {"USD": [{"end": "2025-12-31", "val": 985.5, "filed": "2026-02-15",
                               "form": "10-K", "accn": "a"}]}}
        fs._cache.clear()
        assert total_debt(fs)[0] == 985.5


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


class TestRevenueGrowthTrend:
    """Growth must be current to the latest quarter, and must not be read from a subset tag."""

    @staticmethod
    def quarters(concept, start_year, values, filed_year=2026):
        rows, (y, m) = [], (start_year, 1)
        for v in values:
            end_month = m + 2
            last_day = {3: 31, 6: 30, 9: 30, 12: 31}[end_month]
            rows.append({"start": f"{y}-{m:02d}-01", "end": f"{y}-{end_month:02d}-{last_day}", "val": v,
                         "filed": f"{filed_year}-08-01", "form": "10-Q", "accn": "q"})
            m += 3
            if m > 12:
                y, m = y + 1, 1
        return rows

    def test_steady_growth_reads_as_its_rate(self):
        # 14 quarters growing 10% a year, ending with the Q2 2026 balance sheet
        values = [1e9 * 1.1 ** (i / 4) for i in range(14)]
        fs = build()
        TestAbandonedTags.add(fs, "Revenues", self.quarters("Revenues", 2023, values))
        for concept in ("Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent", "StockholdersEquity"):
            fs._facts["us-gaap"][concept]["units"]["USD"].append(
                {"end": "2026-06-30", "val": 2000.0, "filed": "2026-08-01", "form": "10-Q", "accn": "q"})
        fs._cache.clear()
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["growth_source"] == "3-year quarterly trend"
        assert result["values"]["rev_growth"] == pytest.approx(0.10, abs=0.005)

    def test_a_surge_after_the_last_fiscal_year_is_seen(self):
        # Micron: flat for two years, then revenue quadruples inside the current fiscal year
        values = [5e9] * 10 + [8e9, 13e9, 24e9, 41e9]
        fs = build()
        TestAbandonedTags.add(fs, "Revenues", self.quarters("Revenues", 2023, values))
        for concept in ("Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent", "StockholdersEquity"):
            fs._facts["us-gaap"][concept]["units"]["USD"].append(
                {"end": "2026-06-30", "val": 2000.0, "filed": "2026-08-01", "form": "10-Q", "accn": "q"})
        fs._cache.clear()
        assert compute_metrics(fs, market_cap=5000.0)["values"]["rev_growth"] > 0.3

    def test_quarters_that_disagree_with_the_restated_annual_report_fall_back(self):
        # GE: quarters before a spin-off still carry the old company
        values = [16e9] * 4 + [8e9] * 10
        rows = self.quarters("Revenues", 2023, values)
        # the 10-Ks restate every year on the post-spin basis
        for year in (2022, 2023, 2024, 2025):
            rows.append({"start": f"{year}-01-01", "end": f"{year}-12-31", "val": 32e9, "filed": "2026-02-01",
                         "form": "10-K", "accn": "k"})
        fs = build()
        TestAbandonedTags.add(fs, "Revenues", rows)
        for concept in ("Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent", "StockholdersEquity"):
            fs._facts["us-gaap"][concept]["units"]["USD"].append(
                {"end": "2026-06-30", "val": 2000.0, "filed": "2026-08-01", "form": "10-Q", "accn": "q"})
        fs._cache.clear()
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["growth_source"].startswith("3-fiscal-year CAGR (quarters disagree")
        assert result["values"]["rev_growth"] == pytest.approx(0.0)   # flat on the restated basis

    def test_a_full_year_tagged_as_a_quarter_is_ignored(self):
        from rankfield.metrics import quarterly_revenue
        rows = self.quarters("Revenues", 2025, [5e9, 5e9, 5e9, 5e9])
        rows.append({"start": "2025-10-01", "end": "2025-12-31", "val": 20e9, "filed": "2026-02-01",
                     "form": "10-K", "accn": "k"})   # the 10-K's full year, in a quarter's context
        rows.append({"start": "2025-01-01", "end": "2025-12-31", "val": 20e9, "filed": "2026-02-01",
                     "form": "10-K", "accn": "k"})
        fs = build()
        TestAbandonedTags.add(fs, "Revenues", rows)
        assert dict(quarterly_revenue(fs))[date(2025, 12, 31)] == 5e9

    def test_without_quarterly_history_the_annual_cagr_is_kept(self):
        result = run()   # the fixture company tags annual figures only
        assert result["provenance"]["growth_source"].startswith("3-fiscal-year CAGR")
        # fixture revenue: 1000 in 2025, 850 in 2022
        assert result["values"]["rev_growth"] == pytest.approx((1000 / 850) ** (1 / 3) - 1)

    def test_revenue_is_the_total_not_the_contracts_subset(self):
        # Green Plains: $2.09B total revenue, $0.19B of it from contracts with customers
        fs = build()
        TestAbandonedTags.add(fs, "RevenueFromContractWithCustomerExcludingAssessedTax",
                              [TestAbandonedTags.annual(2025, 190.0)])
        from rankfield.metrics import REVENUE
        assert fs.ttm(REVENUE)["val"] == 1000.0   # the fixture's total Revenues


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
        self.add(fs, "NotesPayableToFormerParent", [self.instant("2025-12-31", 350.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["raw_inputs"]["debt"] is None
        assert result["provenance"]["unmapped_candidates"] == {"debt": ["NotesPayableToFormerParent"]}

    def test_the_singular_service_spelling_of_cost_of_revenue_is_read(self):
        fs = build(CostOfGoodsAndServicesSold=None)
        self.add(fs, "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", [self.annual(2025, 600.0)])
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["values"]["gpoa"] == pytest.approx((1000.0 - 600.0) / 2000.0)


class TestCurrentToTheLatestQuarter:
    """Methodology 1.4: no metric may rest on a fiscal year when newer quarters exist."""

    QUARTER_ENDS = [(y, m, d) for y in range(2021, 2027) for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))
                    if (y, m) <= (2026, 6)]

    def company(self, **quarterly):
        """The fixture company plus quarterly series and a balance sheet at every quarter end."""
        fs = build()
        gaap = fs._facts["us-gaap"]
        for concept, fn in quarterly.items():
            rows = []
            for i, (y, m, d) in enumerate(self.QUARTER_ENDS):
                start_m = m - 2
                rows.append({"start": f"{y}-{start_m:02d}-01", "end": f"{y}-{m:02d}-{d}", "val": fn(i),
                             "filed": "2026-08-01", "form": "10-Q", "accn": "q"})
            gaap[concept] = {"units": {"USD": rows}}
        for concept in ("Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent", "StockholdersEquity"):
            base = gaap[concept]["units"]["USD"][-1]["val"]
            for y, m, d in self.QUARTER_ENDS:
                gaap[concept]["units"]["USD"].append(
                    {"end": f"{y}-{m:02d}-{d}", "val": base, "filed": "2026-08-01", "form": "10-Q", "accn": "q"})
        fs._cache.clear()
        return fs

    def test_rising_gross_profitability_reads_as_an_improvement(self):
        # Micron's shape: gross margin climbing over the last quarters
        fs = self.company(Revenues=lambda i: 1000.0,
                          CostOfGoodsAndServicesSold=lambda i: 700.0 - 15.0 * i)
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["delta_gpoa_source"] == "3-year quarterly trend"
        assert result["values"]["delta_gpoa"] > 0.2

    def test_steady_earnings_have_no_variability(self):
        fs = self.company(NetIncomeLoss=lambda i: 35.0)
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["earn_var_source"] == "5 twelve-month windows to the latest quarter"
        assert result["values"]["earn_var"] == pytest.approx(0.0, abs=1e-12)

    def test_the_latest_year_counts_in_earnings_variability(self):
        # a surge inside the current fiscal year must raise variability
        fs = self.company(NetIncomeLoss=lambda i: 35.0 if i < 20 else 400.0)
        assert compute_metrics(fs, market_cap=5000.0)["values"]["earn_var"] > 0.05

    def test_without_quarterly_history_the_fiscal_year_versions_are_kept(self):
        result = run()
        assert result["provenance"]["delta_gpoa_source"].startswith("fiscal years")
        assert result["provenance"]["earn_var_source"].startswith("5 fiscal years")


class TestDebtFromTheLatestBalanceSheet:
    @staticmethod
    def instant(end, val):
        return {"end": end, "val": val, "filed": "2026-08-01", "form": "10-Q", "accn": "q"}

    def test_a_newer_component_path_beats_an_older_combined_figure(self):
        # Lilly: combined debt tagged in the 10-K, components in every 10-Q
        fs = build()
        fs._facts["us-gaap"]["DebtLongtermAndShorttermCombinedAmount"] = {
            "units": {"USD": [self.instant("2025-12-31", 777.0)]}}
        fs._facts["us-gaap"]["LongTermDebtNoncurrent"]["units"]["USD"].append(self.instant("2026-06-30", 880.0))
        fs._cache.clear()
        assert total_debt(fs) == (880.0, "noncurrent+current+short")

    def test_on_the_same_date_the_combined_figure_still_wins(self):
        fs = build()
        fs._facts["us-gaap"]["DebtLongtermAndShorttermCombinedAmount"] = {
            "units": {"USD": [self.instant("2025-12-31", 777.0)]}}
        fs._cache.clear()
        assert total_debt(fs) == (777.0, "combined-tag")

    def test_a_newer_current_portion_alone_never_replaces_long_term_debt(self):
        # Air Products: long-term debt only in the 10-K; a current portion is not total debt
        fs = build(LongTermDebtNoncurrent=None)
        fs._facts["us-gaap"]["LongTermDebt"] = {"units": {"USD": [self.instant("2025-12-31", 800.0)]}}
        fs._facts["us-gaap"]["LongTermDebtCurrent"] = {"units": {"USD": [self.instant("2026-06-30", 50.0)]}}
        fs._cache.clear()
        assert total_debt(fs) == (800.0, "longtermdebt+short")

    def test_a_newer_partial_tag_does_not_replace_an_older_total(self):
        # TeraWulf: convertible notes alone ($1.1B, June) vs total long-term debt ($3.1B, March)
        fs = build()
        fs._facts["us-gaap"]["LongTermDebtNoncurrent"]["units"]["USD"].append(self.instant("2026-03-31", 3060.0))
        fs._facts["us-gaap"]["ConvertibleDebt"] = {"units": {"USD": [self.instant("2026-06-30", 1102.0)]}}
        fs._cache.clear()
        assert total_debt(fs) == (3060.0, "noncurrent+current+short")


    def test_a_newer_smaller_total_is_a_repayment_not_a_partial_tag(self):
        # CSW Industrials: long-term debt $95M in June 2025 after repaying; an older $872M figure is superseded
        fs = build()
        fs._facts["us-gaap"]["LongTermDebt"] = {"units": {"USD": [self.instant("2025-12-31", 872.0)]}}
        fs._facts["us-gaap"]["LongTermDebtNoncurrent"]["units"]["USD"].append(self.instant("2026-06-30", 95.0))
        fs._cache.clear()
        assert total_debt(fs) == (95.0, "noncurrent+current+short")


class TestGrossProfitabilityGuards:
    company = TestCurrentToTheLatestQuarter.company
    QUARTER_ENDS = TestCurrentToTheLatestQuarter.QUARTER_ENDS

    def test_quarters_that_contradict_the_annual_gross_profit_fall_back(self):
        # Asbury: the early quarters tag a sliver of cost of sales
        fs = self.company(Revenues=lambda i: 250.0, CostOfGoodsAndServicesSold=lambda i: 10.0 if i < 12 else 150.0)
        gaap = fs._facts["us-gaap"]
        for year in (2022, 2023, 2024, 2025):
            gaap["Revenues"]["units"]["USD"].append(
                {"start": f"{year}-01-01", "end": f"{year}-12-31", "val": 1000.0, "filed": "2026-02-01", "form": "10-K", "accn": "k"})
            gaap["CostOfGoodsAndServicesSold"]["units"]["USD"].append(
                {"start": f"{year}-01-01", "end": f"{year}-12-31", "val": 600.0, "filed": "2026-02-01", "form": "10-K", "accn": "k"})
        fs._cache.clear()
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["provenance"]["delta_gpoa_source"].startswith("fiscal years (quarters disagree")


class TestFiscalYearGrossProfitabilityFallback:
    def test_a_cost_tag_that_changes_meaning_leaves_the_metric_missing(self):
        # Asbury: 2022 cost of sales tagged as a small component, 2025 as the full figure
        fs = build(Revenues=1e9, CostOfGoodsAndServicesSold=6e8, Assets=2e9)
        rows = fs._facts["us-gaap"]["CostOfGoodsAndServicesSold"]["units"]["USD"]
        for row in rows:
            if row["end"].startswith(("2021", "2022")):
                row["val"] = 3e7
        fs._cache.clear()
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["values"]["delta_gpoa"] is None
        assert "not comparable" in result["missing"]["delta_gpoa"]

    def test_a_near_zero_revenue_company_keeps_its_wild_margins(self):
        # Pulse Biosciences: margins of -1606% then -54% are real while revenue is tiny
        fs = build()
        rows = fs._facts["us-gaap"]["CostOfGoodsAndServicesSold"]["units"]["USD"]
        for row in rows:
            if row["end"].startswith(("2021", "2022")):
                row["val"] = 30.0
        fs._cache.clear()
        assert compute_metrics(fs, market_cap=5000.0)["values"]["delta_gpoa"] is not None


class TestEarningsVariabilityAroundTheTrend:
    """1.5: steady improvement is not instability; steady decline and cycles are."""

    from rankfield.metrics import variability_around_rising_trend as measure

    def test_steady_improvement_is_stable(self):
        # Palantir's shape: ROA climbing every year
        assert type(self).measure([-0.16, -0.01, 0.08, 0.10, 0.26]) < 0.05
        assert type(self).measure([0.05, 0.10, 0.15, 0.20, 0.25]) == pytest.approx(0.0, abs=1e-12)

    def test_a_steady_decline_counts_in_full(self):
        # Devon's shape: a slide from 23% to 5% is not a stable business
        import statistics
        points = [0.227, 0.205, 0.139, 0.091, 0.046]
        assert type(self).measure(points) == pytest.approx(statistics.stdev(points))

    def test_a_cycle_stays_volatile(self):
        # Micron: into losses and back to a record
        assert type(self).measure([0.152, -0.044, -0.023, 0.079, 0.376]) > 0.15

    def test_flat_earnings_are_stable(self):
        assert type(self).measure([0.176, 0.176, 0.176, 0.176, 0.176]) == pytest.approx(0.0, abs=1e-12)



class TestOperatingIncomeChange:
    """1.6: the latest year's direction of profit, and growth capped by a falling year."""

    company = TestCurrentToTheLatestQuarter.company
    QUARTER_ENDS = TestCurrentToTheLatestQuarter.QUARTER_ENDS

    def test_collapsing_operating_income_reads_as_a_decline(self):
        # Cal-Maine's shape: operating income falling hard over the last four quarters
        fs = self.company(OperatingIncomeLoss=lambda i: 150.0 if i < 18 else 150.0 - 60.0 * (i - 17))
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["values"]["op_inc_change"] < -0.1

    def test_one_bad_quarter_cannot_set_it_alone(self):
        # a single impairment quarter among steady ones: the median ignores it
        fs = self.company(OperatingIncomeLoss=lambda i: -2000.0 if i == len(self.QUARTER_ENDS) - 1 else 150.0)
        assert compute_metrics(fs, market_cap=5000.0)["values"]["op_inc_change"] == pytest.approx(0.0, abs=1e-9)

    def test_revenue_growth_is_averaged_with_a_shrinking_latest_year(self):
        # years of growth, then a fall of 30% over the last four quarters
        fs = self.company(Revenues=lambda i: 1e9 * 1.15 ** i if i < 18 else 1e9 * 1.15 ** 17 * 0.7)
        result = compute_metrics(fs, market_cap=5000.0)
        trend, _ = revenue_trend(fs)
        latest = revenue_latest_year_change(fs)
        assert trend > 0 > latest
        assert result["values"]["rev_growth"] == pytest.approx((trend + latest) / 2)
        assert result["values"]["rev_growth"] < trend * 0.6      # the fall costs it dearly
        assert "average of that and the trend" in result["provenance"]["growth_source"]

    def test_a_shallow_dip_leaves_most_of_the_trend(self):
        # 1.7: a fall of a couple of percent must not erase a rising trend, as the 1.6 cap did
        fs = self.company(Revenues=lambda i: 1e9 * 1.15 ** i if i < 18 else 1e9 * 1.15 ** 17 * 0.8)
        result = compute_metrics(fs, market_cap=5000.0)
        trend, _ = revenue_trend(fs)
        latest = revenue_latest_year_change(fs)
        assert -0.05 < latest < 0 < trend
        assert result["values"]["rev_growth"] > trend * 0.4      # far above the 1.6 cap of `latest`

    def test_it_is_not_applied_to_pre_revenue_companies(self):
        from rankfield.scoring import applicable_metrics
        rows = [{"segment": "pre_revenue", "values": {"op_inc_change": -0.1, "earn_var": 0.2}} for _ in range(5)]
        keys, _ = applicable_metrics(rows)
        assert "op_inc_change" not in keys and "earn_var" in keys


class TestOneOffItemsAreNormalisedBothWays:
    """1.9: a year holding a disposal gain and a write-down is two distortions."""

    company = TestCurrentToTheLatestQuarter.company
    QUARTER_ENDS = TestCurrentToTheLatestQuarter.QUARTER_ENDS

    def steady(self, **extra):
        """Operating income of 150 a quarter, with the last quarter overridden."""
        return self.company(OperatingIncomeLoss=lambda i: 150.0, **extra)

    @staticmethod
    def one_period(fs, concept, value, start, end):
        fs._facts["us-gaap"][concept] = {"units": {"USD": [
            {"start": start, "end": end, "val": value, "filed": "2026-08-01", "form": "10-Q", "accn": "q"}]}}
        fs._cache.clear()
        return fs

    def test_a_write_down_is_added_back(self):
        # Molson Coors, Centene, Owens Corning: one impairment quarter turns a
        # profitable business into a reported loss-maker
        fs = self.company(OperatingIncomeLoss=lambda i: 150.0 if i < len(self.QUARTER_ENDS) - 1 else -1000.0)
        self.one_period(fs, "GoodwillImpairmentLoss", 1150.0, "2026-04-01", "2026-06-30")
        before, _, _ = _ebit(fs)
        after, note = normalised_ebit(fs, before)
        assert before < 0 < after
        assert after == pytest.approx(before + 1150.0)
        assert "one-off charge" in note

    def test_a_disposal_gain_is_taken_out(self):
        # CareDx: the whole year's operating profit is the sale of a business
        fs = self.company(OperatingIncomeLoss=lambda i: 10.0 if i < len(self.QUARTER_ENDS) - 1 else 900.0)
        self.one_period(fs, "GainLossOnSaleOfBusiness", 880.0, "2026-04-01", "2026-06-30")
        before, _, _ = _ebit(fs)
        after, note = normalised_ebit(fs, before)
        assert after == pytest.approx(before - 880.0)
        assert "one-off gain" in note

    def test_a_gain_and_a_larger_charge_are_netted(self):
        # General Mills: a $1,054M disposal gain inside a year holding a $2,971M
        # write-down. Removing only the gain would report a loss that never was.
        fs = self.company(OperatingIncomeLoss=lambda i: 150.0 if i < len(self.QUARTER_ENDS) - 1 else -900.0)
        self.one_period(fs, "GainLossOnSaleOfBusiness", 300.0, "2025-10-01", "2025-12-31")
        fs._facts["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"][-3]["val"] = 450.0   # the gain quarter
        self.one_period(fs, "AssetImpairmentCharges", 1050.0, "2026-04-01", "2026-06-30")
        before, _, _ = _ebit(fs)
        after, note = normalised_ebit(fs, before)
        assert after == pytest.approx(before + 1050.0 - 300.0)
        assert "one-off gain" in note and "one-off charge" in note

    def test_an_item_the_operating_line_never_shows_is_left_alone(self):
        # a footnote disclosure, or a gain booked below the operating line:
        # deducting it would punish the company for a number it never counted
        fs = self.steady()
        self.one_period(fs, "GainLossOnSaleOfBusiness", 400.0, "2026-04-01", "2026-06-30")
        before, _, _ = _ebit(fs)
        after, note = normalised_ebit(fs, before)
        assert after == before and note is None

    def test_an_immaterial_item_is_left_alone(self):
        fs = self.company(OperatingIncomeLoss=lambda i: 150.0 if i < len(self.QUARTER_ENDS) - 1 else 100.0)
        self.one_period(fs, "RestructuringCharges", 50.0, "2026-04-01", "2026-06-30")
        before, _, _ = _ebit(fs)
        after, note = normalised_ebit(fs, before)
        assert after == before and note is None

    def test_an_item_from_an_earlier_year_is_out_of_the_window(self):
        fs = self.company(OperatingIncomeLoss=lambda i: 150.0 if i != 8 else -1000.0)
        self.one_period(fs, "GoodwillImpairmentLoss", 1150.0, "2023-04-01", "2023-06-30")
        before, _, _ = _ebit(fs)
        after, note = normalised_ebit(fs, before)
        assert after == before and note is None

    def test_the_adjustment_reaches_the_metrics_that_use_ebit(self):
        fs = self.company(OperatingIncomeLoss=lambda i: 150.0 if i < len(self.QUARTER_ENDS) - 1 else -1000.0)
        self.one_period(fs, "GoodwillImpairmentLoss", 1150.0, "2026-04-01", "2026-06-30")
        result = compute_metrics(fs, market_cap=5000.0)
        assert result["values"]["roic"] > 0
        assert result["values"]["ebit_ev"] > 0
        assert "normalised for" in result["provenance"]["ebit_source"]
