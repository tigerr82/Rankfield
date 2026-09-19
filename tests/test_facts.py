"""Point-in-time fact selection.

The single rule this file defends: when scoring as of date D, only facts with
`filed <= D` exist. If that leaks, every historical score becomes unreproducible
and any backtest silently uses information nobody had at the time.
"""
from datetime import date

from rankfield.facts import FactSet


def facts(*entries, taxonomy="us-gaap"):
    """Build a companyfacts-shaped payload from (concept, unit, rows) triples."""
    out = {}
    for concept, unit, rows in entries:
        out.setdefault(concept, {"units": {}})["units"].setdefault(unit, []).extend(rows)
    return {"entityName": "Test Co", "facts": {taxonomy: out}}


def q(start, end, val, filed, form="10-Q", accn="x"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "accn": accn}


def instant(end, val, filed, form="10-Q", accn="x"):
    return {"end": end, "val": val, "filed": filed, "form": form, "accn": accn}


AS_OF = date(2026, 8, 31)


class TestPointInTime:
    def test_a_fact_filed_after_the_scoring_date_is_invisible(self):
        payload = facts(("Assets", "USD", [
            instant("2026-03-31", 100, filed="2026-04-30"),
            instant("2026-06-30", 999, filed="2026-09-15"),  # filed AFTER as_of
        ]))
        fs = FactSet(payload, AS_OF)
        assert fs.instant(["Assets"])["val"] == 100

    def test_a_restatement_filed_later_wins_once_it_is_public(self):
        payload = facts(("Assets", "USD", [
            instant("2026-03-31", 100, filed="2026-04-30", accn="orig"),
            instant("2026-03-31", 120, filed="2026-07-30", accn="restated"),
        ]))
        assert FactSet(payload, AS_OF).instant(["Assets"])["val"] == 120

    def test_the_same_restatement_is_invisible_before_it_was_filed(self):
        payload = facts(("Assets", "USD", [
            instant("2026-03-31", 100, filed="2026-04-30", accn="orig"),
            instant("2026-03-31", 120, filed="2026-07-30", accn="restated"),
        ]))
        # Scoring in May can only see the original figure.
        assert FactSet(payload, date(2026, 5, 31)).instant(["Assets"])["val"] == 100

    def test_a_period_end_after_the_scoring_date_is_not_used(self):
        payload = facts(("Assets", "USD", [
            instant("2026-06-30", 100, filed="2026-07-30"),
            instant("2026-12-31", 500, filed="2026-08-01"),  # filed early, ends later
        ]))
        assert FactSet(payload, AS_OF).instant(["Assets"])["val"] == 100


class TestTagPriority:
    def test_the_first_tag_that_resolves_a_period_wins(self):
        payload = facts(
            ("Revenues", "USD", [q("2026-01-01", "2026-03-31", 50, "2026-04-30")]),
            ("RevenueFromContractWithCustomerExcludingAssessedTax", "USD",
             [q("2026-01-01", "2026-03-31", 70, "2026-04-30")]),
        )
        fs = FactSet(payload, AS_OF)
        rows = fs.durations([
            "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])
        assert [r["val"] for r in rows] == [70]

    def test_a_lower_priority_tag_fills_a_period_the_first_never_reported(self):
        payload = facts(
            ("RevenueFromContractWithCustomerExcludingAssessedTax", "USD",
             [q("2026-01-01", "2026-03-31", 70, "2026-04-30")]),
            ("Revenues", "USD", [q("2025-01-01", "2025-03-31", 40, "2025-04-30")]),
        )
        fs = FactSet(payload, AS_OF)
        vals = {r["end"]: r["val"] for r in fs.durations(
            ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])}
        assert vals == {"2026-03-31": 70, "2025-03-31": 40}


class TestTTM:
    def test_four_quarters_tile_into_a_trailing_year(self):
        payload = facts(("Revenues", "USD", [
            q("2025-07-01", "2025-09-30", 10, "2025-10-30"),
            q("2025-10-01", "2025-12-31", 20, "2026-01-30"),
            q("2026-01-01", "2026-03-31", 30, "2026-04-30"),
            q("2026-04-01", "2026-06-30", 40, "2026-07-30"),
        ]))
        ttm = FactSet(payload, AS_OF).ttm(["Revenues"])
        assert ttm["val"] == 100
        assert ttm["basis"] == "ttm"
        assert ttm["end"] == "2026-06-30"

    def test_a_year_to_date_filer_is_decomposed_into_its_missing_stubs(self):
        # Cash-flow items are commonly tagged only cumulatively. Differencing
        # consecutive year-to-date figures recovers each quarter, which is what
        # makes a trailing twelve months possible at all.
        payload = facts(("NetCashProvidedByUsedInOperatingActivities", "USD", [
            q("2025-01-01", "2025-06-30", 40, "2025-07-30"),    # H1 -> Q3 = 75-40
            q("2025-01-01", "2025-09-30", 75, "2025-10-30"),    # 9M -> Q4 = 100-75
            q("2025-01-01", "2025-12-31", 100, "2026-02-15", form="10-K"),
            q("2026-01-01", "2026-03-31", 30, "2026-04-30"),
            q("2026-01-01", "2026-06-30", 65, "2026-07-30"),    # H1 -> Q2 = 65-30
        ]))
        ttm = FactSet(payload, AS_OF).ttm(["NetCashProvidedByUsedInOperatingActivities"])
        # Q3-25 (35) + Q4-25 (25) + Q1-26 (30) + Q2-26 (35) = 125
        assert ttm["val"] == 125
        assert ttm["basis"] == "ttm"

    def test_an_untileable_year_falls_back_rather_than_reporting_a_partial_sum(self):
        # Without H1-2025 there is no way to recover Q3-2025, so a true trailing
        # year is not computable. Reporting the annual figure is correct;
        # reporting a nine-month sum as if it were a year would not be.
        payload = facts(("Revenues", "USD", [
            q("2025-01-01", "2025-09-30", 75, "2025-10-30"),
            q("2025-01-01", "2025-12-31", 100, "2026-02-15", form="10-K"),
            q("2026-01-01", "2026-06-30", 65, "2026-07-30"),
        ]))
        ttm = FactSet(payload, AS_OF).ttm(["Revenues"])
        assert ttm["val"] == 100
        assert ttm["basis"] == "fy"

    def test_falls_back_to_the_last_annual_figure_when_quarters_do_not_tile(self):
        payload = facts(("Revenues", "USD", [
            q("2025-01-01", "2025-12-31", 500, "2026-02-15", form="10-K"),
        ]))
        ttm = FactSet(payload, AS_OF).ttm(["Revenues"])
        assert ttm["val"] == 500
        # A lone annual fact is the last annual report, not a stitched trailing
        # figure - and it must be labelled the same way whichever code path
        # produced it.
        assert ttm["basis"] == "fy"

    def test_no_duration_facts_gives_none(self):
        assert FactSet(facts(), AS_OF).ttm(["Revenues"]) is None

    def test_a_partial_year_is_not_passed_off_as_a_full_one(self):
        # Two quarters must not be reported as a trailing twelve months.
        payload = facts(("Revenues", "USD", [
            q("2026-01-01", "2026-03-31", 30, "2026-04-30"),
            q("2026-04-01", "2026-06-30", 40, "2026-07-30"),
        ]))
        assert FactSet(payload, AS_OF).ttm(["Revenues"]) is None


class TestAnnualSeries:
    def test_returns_fiscal_years_newest_first(self):
        payload = facts(("Revenues", "USD", [
            q("2023-01-01", "2023-12-31", 10, "2024-02-15", form="10-K"),
            q("2024-01-01", "2024-12-31", 20, "2025-02-15", form="10-K"),
            q("2025-01-01", "2025-12-31", 30, "2026-02-15", form="10-K"),
        ]))
        series = FactSet(payload, AS_OF).annual_series(["Revenues"], 5)
        assert [r["val"] for r in series] == [30, 20, 10]

    def test_quarters_are_not_mistaken_for_years(self):
        payload = facts(("Revenues", "USD", [
            q("2026-01-01", "2026-03-31", 5, "2026-04-30"),
        ]))
        assert FactSet(payload, AS_OF).annual_series(["Revenues"], 5) == []

    def test_a_fiscal_year_change_does_not_produce_two_entries_for_one_year(self):
        # Aligned on period END dates, not fiscal labels.
        payload = facts(("Revenues", "USD", [
            q("2024-07-01", "2025-06-30", 100, "2025-08-15", form="10-K"),
            q("2025-01-01", "2025-12-31", 130, "2026-02-15", form="10-K"),
        ]))
        series = FactSet(payload, AS_OF).annual_series(["Revenues"], 5)
        assert len(series) == 1  # ends are 184 days apart - the same year


class TestStructuralSignals:
    def test_a_domestic_filer_is_recognised(self):
        payload = facts(("Assets", "USD", [
            instant("2026-03-31", 1, "2026-04-30", form="10-Q", accn="a"),
            instant("2025-12-31", 1, "2026-02-15", form="10-K", accn="b"),
        ]))
        fs = FactSet(payload, AS_OF)
        assert fs.files_domestic_forms is True
        assert fs.quarters_filed == 2

    def test_a_foreign_private_issuer_is_not(self):
        payload = facts(("Assets", "USD", [
            instant("2025-12-31", 1, "2026-04-30", form="20-F", accn="a"),
        ]))
        assert FactSet(payload, AS_OF).files_domestic_forms is False

    def test_an_empty_payload_does_not_raise(self):
        fs = FactSet({"facts": {}}, AS_OF)
        assert fs.quarters_filed == 0
        assert fs.files_domestic_forms is False
        assert fs.instant(["Assets"]) is None


class TestOnlyFinancialReportsSupplyFigures:
    """A proxy statement filed after the 10-K must not replace the audited figure.

    Pay-versus-performance tables in DEF 14A filings carry XBRL-tagged net income,
    often at the wrong scale. With "latest filed wins", G-III's net income arrived
    ~1000x too small and its earnings looked perfectly stable.
    """

    def test_a_proxy_statement_cannot_replace_an_audited_annual_figure(self):
        payload = facts(("NetIncomeLoss", "USD", [
            q("2023-02-01", "2024-01-31", 176_168_000, "2024-03-25", form="10-K"),
            q("2023-02-01", "2024-01-31", 174_740, "2026-05-05", form="DEF 14A"),
        ]))
        series = FactSet(payload, AS_OF).annual_series(["NetIncomeLoss"], 5)
        assert [r["val"] for r in series] == [176_168_000]

    def test_an_amended_annual_report_still_supersedes_the_original(self):
        payload = facts(("NetIncomeLoss", "USD", [
            q("2024-01-01", "2024-12-31", 100, "2025-02-15", form="10-K"),
            q("2024-01-01", "2024-12-31", 90, "2025-06-01", form="10-K/A"),
        ]))
        assert FactSet(payload, AS_OF).annual_series(["NetIncomeLoss"], 5)[0]["val"] == 90

    def test_a_period_reported_only_outside_financial_reports_resolves_nothing(self):
        payload = facts(("NetIncomeLoss", "USD", [
            q("2024-01-01", "2024-12-31", 5, "2025-04-01", form="DEF 14A"),
        ]))
        assert FactSet(payload, AS_OF).annual_series(["NetIncomeLoss"], 5) == []


class TestAbandonedTagsAreNotCurrent:
    """EDGAR keeps every tag a filer ever used, so a tag's latest value can be a decade old.

    Microsoft's combined-debt tag stops in March 2015; its debt has been reported
    under other tags since. Read by priority, the 2015 figure stood in for 2026.
    """

    @staticmethod
    def balance_sheet(end, filed, form="10-Q"):
        """A full balance sheet: the reference date needs several tags sharing it."""
        return tuple(
            (concept, "USD", [instant(end, 1000, filed, form=form)])
            for concept in ("Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent", "StockholdersEquity")
        )

    BALANCE_SHEET = balance_sheet.__func__("2026-06-30", "2026-07-30")

    def test_an_abandoned_tag_does_not_stand_in_for_todays_value(self):
        payload = facts(*self.BALANCE_SHEET, ("DebtLongtermAndShorttermCombinedAmount", "USD", [
            instant("2015-03-31", 31_800, "2015-04-23"),
        ]))
        fs = FactSet(payload, AS_OF)
        assert fs.instant(["DebtLongtermAndShorttermCombinedAmount"]) is None
        assert fs.stale_inputs == [
            {"concept": "DebtLongtermAndShorttermCombinedAmount", "last_reported": "2015-03-31"}
        ]

    def test_a_tag_still_in_use_is_returned_and_nothing_is_flagged(self):
        payload = facts(*self.BALANCE_SHEET, ("LongTermDebtNoncurrent", "USD", [
            instant("2026-06-30", 31_067, "2026-07-30"),
        ]))
        fs = FactSet(payload, AS_OF)
        assert fs.instant(["LongTermDebtNoncurrent"])["val"] == 31_067
        assert fs.stale_inputs == []

    def test_a_trailing_figure_from_an_abandoned_tag_is_none(self):
        payload = facts(*self.BALANCE_SHEET, ("OperatingIncomeLoss", "USD", [
            q("2014-01-01", "2014-12-28", 20_000, "2015-02-20", form="10-K"),
        ]))
        assert FactSet(payload, AS_OF).ttm(["OperatingIncomeLoss"]) is None

    def test_an_annual_only_figure_three_quarters_old_is_still_current(self):
        # June fiscal year, tagged only in the 10-K; the latest balance sheet is Q3.
        payload = facts(
            *self.balance_sheet("2026-03-31", "2026-05-01"),
            ("DepreciationDepletionAndAmortization", "USD", [
                q("2024-07-01", "2025-06-30", 50, "2025-08-20", form="10-K"),
            ]),
        )
        ttm = FactSet(payload, AS_OF).ttm(["DepreciationDepletionAndAmortization"])
        assert ttm["val"] == 50
        assert ttm["basis"] == "fy"

    def test_an_annual_series_ending_in_an_abandoned_tag_is_empty(self):
        payload = facts(*self.BALANCE_SHEET, ("GrossProfit", "USD", [
            q(f"{y}-01-01", f"{y}-12-31", 100, f"{y + 1}-02-15", form="10-K") for y in (2016, 2017, 2018, 2019)
        ]))
        assert FactSet(payload, AS_OF).annual_series(["GrossProfit"], 5) == []

    def test_a_prior_year_lookup_is_judged_against_its_own_date(self):
        payload = facts(*self.BALANCE_SHEET, ("LongTermDebtNoncurrent", "USD", [
            instant("2016-06-30", 90, "2016-07-30"),
            instant("2025-06-30", 500, "2025-07-30"),
        ]))
        fs = FactSet(payload, AS_OF)
        assert fs.instant(["LongTermDebtNoncurrent"], on_or_before=date(2025, 6, 30))["val"] == 500
        assert fs.instant(["LongTermDebtNoncurrent"], on_or_before=date(2024, 6, 30)) is None
        # a year older than the 2026-06-30 balance sheet: not today's debt
        assert fs.instant(["LongTermDebtNoncurrent"]) is None

    def test_the_reference_date_survives_an_abandoned_assets_tag(self):
        # Cinemark: consolidated Assets last tagged 2022, full balance sheets since.
        payload = facts(
            ("Assets", "USD", [instant("2022-09-30", 900, "2022-11-01")]),
            *[(c, "USD", [instant("2026-03-31", 10, "2026-05-01")])
              for c in ("Goodwill", "AssetsCurrent", "LiabilitiesCurrent", "LongTermDebtFairValue", "InventoryNet")],
            ("OperatingIncomeLoss", "USD", [q("2021-07-01", "2022-06-30", 50, "2022-08-05", form="10-K")]),
        )
        fs = FactSet(payload, AS_OF)
        assert fs.reference_end == date(2026, 3, 31)
        assert fs.ttm(["OperatingIncomeLoss"]) is None

    def test_a_balance_sheet_dated_after_its_own_filing_is_a_typo(self):
        # H.B. Fuller tags some deferred-tax facts as of 2105.
        payload = facts(
            *self.balance_sheet("2026-05-30", "2026-06-25"),
            *[(c, "USD", [instant("2105-11-28", 1, "2026-01-20", form="10-K")])
              for c in ("DeferredTaxAssetsNet", "DeferredTaxAssetsGross", "DeferredIncomeTaxLiabilities",
                        "DeferredTaxAssetsLiabilitiesNet", "PercentageOfLIFOInventory")],
        )
        assert FactSet(payload, AS_OF).reference_end == date(2026, 5, 30)

    def test_a_quarterly_figure_that_stopped_three_quarters_ago_is_stale(self):
        # H.B. Fuller: operating income tagged quarterly until August 2025,
        # latest 10-Q May 2026. A 300-day allowance is for annual-only figures.
        quarters = [("2024-09-01", "2024-11-30"), ("2024-12-01", "2025-03-01"),
                    ("2025-03-02", "2025-05-31"), ("2025-06-01", "2025-08-30")]
        payload = facts(
            *self.balance_sheet("2026-05-30", "2026-06-25"),
            ("OperatingIncomeLoss", "USD", [q(s, e, 25, "2025-09-25") for s, e in quarters]),
        )
        fs = FactSet(payload, AS_OF)
        assert fs.ttm(["OperatingIncomeLoss"]) is None
        assert fs.stale_inputs == [{"concept": "OperatingIncomeLoss", "last_reported": "2025-08-30"}]

    def test_without_a_balance_sheet_there_is_nothing_to_measure_age_against(self):
        payload = facts(("Revenues", "USD", [q("2014-01-01", "2014-12-31", 7, "2015-02-15", form="10-K")]))
        assert FactSet(payload, AS_OF).ttm(["Revenues"])["val"] == 7


class TestNestedRevenueTags:
    """Revenue tags nest, so the largest is the total - within one filing, never across a restatement."""

    def fs(self, *entries):
        FactSet.LARGEST_WINS.add(("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"))
        return FactSet(facts(*entries), AS_OF)

    def test_the_total_beats_the_contracts_subset_in_the_same_filing(self):
        # Green Plains: $2.09B total, $0.19B of it from contracts with customers
        fs = self.fs(
            ("RevenueFromContractWithCustomerExcludingAssessedTax", "USD",
             [q("2025-01-01", "2025-12-31", 190, "2026-02-20", form="10-K")]),
            ("Revenues", "USD", [q("2025-01-01", "2025-12-31", 2090, "2026-02-20", form="10-K")]),
        )
        rows = fs.durations(["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])
        assert [r["val"] for r in rows] == [2090]

    def test_a_restated_period_is_not_overridden_by_an_older_filings_total(self):
        # Crane NXT: 2022 restated to $1.3B after the separation; the old $3.4B is pre-separation Crane
        fs = self.fs(
            ("RevenueFromContractWithCustomerExcludingAssessedTax", "USD",
             [q("2022-01-01", "2022-12-31", 1300, "2025-02-20", form="10-K")]),
            ("Revenues", "USD", [q("2022-01-01", "2022-12-31", 3400, "2023-02-20", form="10-K")]),
        )
        rows = fs.durations(["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])
        assert [r["val"] for r in rows] == [1300]
