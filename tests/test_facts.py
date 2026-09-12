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
