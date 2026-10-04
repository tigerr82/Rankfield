"""Segmentation, composite renormalisation, deciles and the weight sweep."""
import pytest

from rankfield.scoring import (
    applicable_metrics,
    assign_sector_deciles,
    classify_segment,
    composite_of,
    peer_group,
    rank_stability,
    score_segment,
    weight_combinations,
)

EQUAL = {"quality": 25, "growth": 25, "valuation": 25, "health": 25}


class TestCompositeOf:
    def test_equal_weights_average_the_factors(self):
        assert composite_of({"quality": 80, "growth": 60, "valuation": 40, "health": 20}, EQUAL) == 50.0

    def test_a_missing_factor_renormalises_rather_than_scoring_zero(self):
        # The whole point: a null factor must not drag the composite down as if
        # it were a zero. 80/60/40 with health missing is 60, not 45.
        renormalised = composite_of({"quality": 80, "growth": 60, "valuation": 40, "health": None}, EQUAL)
        imputed_as_zero = composite_of({"quality": 80, "growth": 60, "valuation": 40, "health": 0}, EQUAL)
        assert renormalised == 60.0
        assert imputed_as_zero == 45.0
        assert renormalised > imputed_as_zero

    def test_all_factors_missing_gives_none(self):
        assert composite_of(dict.fromkeys(EQUAL, None), EQUAL) is None

    def test_zero_weighted_factors_are_excluded(self):
        weights = {"quality": 100, "growth": 0, "valuation": 0, "health": 0}
        assert composite_of({"quality": 70, "growth": 10, "valuation": 10, "health": 10}, weights) == 70.0

    def test_all_weights_zero_gives_none_not_a_division_error(self):
        assert composite_of({"quality": 70, "growth": 10, "valuation": 10, "health": 10},
                            dict.fromkeys(EQUAL, 0)) is None

    def test_weights_need_not_sum_to_one_hundred(self):
        # The UI lets sliders total anything; normalisation is automatic.
        a = composite_of({"quality": 100, "growth": 0, "valuation": None, "health": None}, {"quality": 10, "growth": 10, "valuation": 10, "health": 10})
        b = composite_of({"quality": 100, "growth": 0, "valuation": None, "health": None}, {"quality": 50, "growth": 50, "valuation": 50, "health": 50})
        assert a == b == 50.0


class TestClassifySegment:
    def test_a_bank_is_a_financial(self):
        assert classify_segment({"sector": "Finance", "industry": "Major Banks"}, 1e9) == "financials"

    def test_a_reit_has_its_own_segment(self):
        # 2.0: depreciation on buildings that hold their value makes an
        # earnings-based score mark the whole asset class down
        assert classify_segment(
            {"sector": "Real Estate", "industry": "Real Estate Investment Trusts"}, 1e9
        ) == "reits"

    def test_a_bank_is_a_financial_and_not_a_reit(self):
        assert classify_segment({"sector": "Finance", "industry": "Major Banks"}, 1e10) == "financials"
        assert classify_segment({"sector": "Finance", "industry": "Life Insurance"}, 1e10) == "financials"

    def test_an_education_company_misfiled_under_real_estate_is_an_operating_company(self):
        # Nasdaq files Grand Canyon, Stride, Perdoceo and Strayer under
        # "Real Estate" with industry "Other Consumer Services". Segmenting on
        # sector alone put them at the top of the Financials table - exactly the
        # cross-sector comparison the design exists to prevent.
        assert classify_segment(
            {"sector": "Real Estate", "industry": "Other Consumer Services"}, 5e8
        ) == "operating"

    def test_a_homebuilder_is_an_operating_company(self):
        assert classify_segment({"sector": "Real Estate", "industry": "Homebuilding"}, 1e9) == "operating"

    def test_pre_revenue_biotech_is_segregated(self):
        assert classify_segment({"sector": "Health Care", "industry": "Biotechnology"}, None) == "pre_revenue"
        assert classify_segment({"sector": "Health Care", "industry": "Biotechnology"}, 1_000_000) == "pre_revenue"

    def test_a_biotech_with_real_revenue_is_an_operating_company(self):
        assert classify_segment({"sector": "Health Care", "industry": "Biotechnology"}, 5e9) == "operating"

    def test_missing_sector_and_industry_default_to_operating(self):
        assert classify_segment({"sector": None, "industry": None}, 1e9) == "operating"


class TestApplicableMetrics:
    def test_a_metric_nobody_resolves_is_dropped_from_the_segment(self):
        rows = [{"values": {"roic": 0.1, "gpoa": None}} for _ in range(10)]
        keys, resolution = applicable_metrics(rows, min_resolution=0.4)
        assert "roic" in keys
        assert "gpoa" not in keys
        assert resolution["gpoa"] == 0.0

    def test_a_widely_resolved_metric_is_kept(self):
        rows = [{"values": {"roic": 0.1}} for _ in range(10)]
        keys, _ = applicable_metrics(rows, min_resolution=0.4)
        assert "roic" in keys

    def test_empty_segment_does_not_divide_by_zero(self):
        keys, resolution = applicable_metrics([], min_resolution=0.4)
        assert keys == []
        assert all(v == 0.0 for v in resolution.values())


class TestSectorDeciles:
    def test_deciles_are_assigned_within_a_sector_not_globally(self):
        rows = [
            {"listing": {"sector": "Tech"}, "composite": 100 - i, "ticker": f"T{i}"} for i in range(20)
        ] + [
            {"listing": {"sector": "Energy"}, "composite": 50 - i, "ticker": f"E{i}"} for i in range(20)
        ]
        assign_sector_deciles(rows)
        best_tech = next(r for r in rows if r["ticker"] == "T0")
        best_energy = next(r for r in rows if r["ticker"] == "E0")
        # Energy's best scores 50 - far below every Tech name - yet it is still
        # top decile of its own sector. A global cut would erase the sector.
        assert best_tech["sector_decile"] == 1
        assert best_energy["sector_decile"] == 1

    def test_rows_without_a_composite_get_no_decile(self):
        rows = [{"listing": {"sector": "Tech"}, "composite": None, "ticker": "X"}]
        assign_sector_deciles(rows)
        assert rows[0]["sector_decile"] is None

    def test_deciles_stay_within_one_to_ten(self):
        rows = [{"listing": {"sector": "Tech"}, "composite": 100 - i, "ticker": str(i)} for i in range(137)]
        assign_sector_deciles(rows)
        assert {r["sector_decile"] for r in rows} <= set(range(1, 11))


class TestWeightSweep:
    def test_every_combination_sums_to_one_hundred(self):
        combos = weight_combinations([10, 15, 20, 25, 30, 35, 40])
        assert combos
        assert all(sum(c.values()) == 100 for c in combos)

    def test_the_default_weighting_is_included(self):
        assert EQUAL in weight_combinations([10, 15, 20, 25, 30, 35, 40])

    def test_stability_brackets_the_actual_rank(self):
        scored = [
            {"ticker": "A", "factors": {"quality": 95, "growth": 95, "valuation": 95, "health": 95}},
            # B and C are mirror images: each wins on the factor the other loses,
            # so which of them ranks higher depends entirely on the weighting.
            {"ticker": "B", "factors": {"quality": 90, "growth": 90, "valuation": 10, "health": 10}},
            {"ticker": "C", "factors": {"quality": 10, "growth": 10, "valuation": 90, "health": 90}},
        ]
        rank_stability(scored, [10, 20, 25, 30, 40])
        a, b = scored[0]["stability"], scored[1]["stability"]
        # A dominates on every factor, so its rank cannot move at all.
        assert a["rank_min"] == a["rank_max"] == 1
        assert a["score"] == 1.0
        # B only leads under weightings that favour quality and growth.
        assert b["rank_min"] == 2 and b["rank_max"] == 3
        assert b["score"] < 1.0

    def test_stability_on_an_empty_table_is_a_no_op(self):
        rank_stability([], [10, 25, 40])  # must not raise


class TestScoreSegmentEndToEnd:
    def _rows(self, n=30):
        rows = []
        for i in range(n):
            rows.append({
                "ticker": f"T{i}",
                "listing": {"sector": "Tech", "industry": "Software"},
                "values": {
                    "roic": 0.05 + i * 0.01,
                    "gpoa": 0.10 + i * 0.01,
                    "earn_var": 0.20 - i * 0.005,
                    "ebit_ev": 0.02 + i * 0.002,
                    "ebitda_ev": 0.03 + i * 0.002,
                    "fcf_ev": 0.01 + i * 0.002,
                    "delta_gpoa": 0.01 * i,
                    "rev_growth": 0.02 * i,
                    "debt_equity": 2.0 - i * 0.05,
                    "net_debt_ebitda": 4.0 - i * 0.1,
                    "altman_z": 1.0 + i * 0.2,
                },
                "missing": {},
            })
        return rows

    def test_the_strongest_companies_rank_first(self):
        result = score_segment(self._rows(), weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        top_two = {r["ticker"] for r in result["scored"][:2]}
        assert top_two == {"T28", "T29"}
        assert result["scored"][0]["rank"] == 1
        composites = [r["composite"] for r in result["scored"]]
        assert composites == sorted(composites, reverse=True)

    def test_shrinking_below_the_hurdle_is_not_rewarded_as_growth(self):
        # A straight inversion made the weakest grower among value-destroyers
        # the best "grower" in the table. Below the hurdle growth is capped at the
        # midpoint whichever way revenue moves.
        result = score_segment(self._rows(), weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        by_ticker = {r["ticker"]: r for r in result["scored"]}
        # T0: the lowest revenue growth, ROIC under the hurdle.
        assert by_ticker["T0"]["factors"]["growth"] <= 50
        assert by_ticker["T0"]["factors"]["growth"] < by_ticker["T29"]["factors"]["growth"]

    def test_fast_growth_below_the_hurdle_is_capped_not_inverted(self):
        rows = self._rows()
        by = {r["ticker"]: r for r in rows}
        by["T29"]["values"]["roic"] = 0.05   # fastest grower, now destroying value
        result = score_segment(rows, weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        top = next(r for r in result["scored"] + result["insufficient"] if r["ticker"] == "T29")
        # 2.1: never above the midpoint, and never the mirror image of the
        # measurement - a raw 98 used to come back as 2.
        assert top["factors"]["growth"] <= 50
        assert top["percentiles"]["rev_growth"] == 50.0

    def test_no_growth_score_below_the_hurdle_exceeds_the_midpoint(self):
        result = score_segment(self._rows(), weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        for r in result["scored"]:
            if "below-hurdle" in (r["bases"].get("rev_growth") or ""):
                assert r["factors"]["growth"] <= 50

    def test_winsorization_ties_the_extremes_before_ranking(self):
        # 5/95 clipping is supposed to collapse the tail, so the very best names
        # share a percentile rather than one of them running away with it. That
        # is the documented intent - one extreme ratio must not set the scale.
        result = score_segment(self._rows(), weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        assert result["scored"][0]["composite"] == result["scored"][1]["composite"]
        # ... and without clipping they would separate.
        unclipped = score_segment(self._rows(), weights=EQUAL, winsor=(0, 100), roic_hurdle=0.09,
                                  min_cohort=8, coverage_threshold=0.7)
        assert unclipped["scored"][0]["composite"] > unclipped["scored"][1]["composite"]

    def test_growth_is_inverted_below_the_roic_hurdle(self):
        rows = self._rows()
        result = score_segment(rows, weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        by_ticker = {r["ticker"]: r for r in result["scored"]}
        # T0 has the lowest ROIC (5%, under the 9% hurdle) but growth metrics at
        # the bottom of the cohort. Below the hurdle its growth score is capped.
        assert "below-hurdle" in (by_ticker["T0"]["bases"]["rev_growth"] or "")
        # T29 clears the hurdle comfortably, so its percentile is used as-is.
        assert "below-hurdle" not in (by_ticker["T29"]["bases"]["rev_growth"] or "")

    def test_growth_drops_out_when_roic_is_unknown(self):
        rows = self._rows()
        for r in rows[:5]:
            r["values"]["roic"] = None
        result = score_segment(rows, weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        target = next(r for r in result["scored"] + result["insufficient"] if r["ticker"] == "T0")
        assert target["percentiles"]["rev_growth"] is None
        assert "ROIC unavailable" in target["missing"]["rev_growth"]

    def test_a_thin_cohort_falls_back_to_the_whole_segment(self):
        rows = self._rows(30)
        for r in rows[:3]:
            r["listing"] = {"sector": "Tiny", "industry": "Software"}
        result = score_segment(rows, weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        assert "(segment-wide)" in result["cohorts"]
        target = next(r for r in result["scored"] if r["ticker"] == "T0")
        assert target["bases"]["roic"].startswith("universe")

    def test_low_coverage_is_routed_out_rather_than_low_scored(self):
        rows = self._rows()
        for key in ("roic", "gpoa", "earn_var", "ebit_ev", "ebitda_ev", "fcf_ev", "delta_gpoa", "rev_growth"):
            rows[0]["values"][key] = None
        result = score_segment(rows, weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        assert rows[0]["ticker"] not in [r["ticker"] for r in result["scored"]]
        routed = next(r for r in result["insufficient"] if r["ticker"] == "T0")
        assert "resolved" in routed["insufficient_reason"]
        assert "composite" not in routed  # never given a score at all

    def test_ranks_are_dense_and_start_at_one(self):
        result = score_segment(self._rows(), weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        assert [r["rank"] for r in result["scored"]] == list(range(1, len(result["scored"]) + 1))


class TestFactorCompositionV11:
    """Methodology 1.1: Growth is revenue growth alone; dGPOA is a Quality metric.

    dGPOA measures efficiency, not growth. While it sat in Growth, a company that
    held its assets flat while selling a little more outscored faster revenue
    growers on "Growth" - Adobe at 10.5% beat Alphabet (12.5%) and Microsoft
    (16.1%). These tests stop that composition coming back.
    """

    def test_growth_is_revenue_growth_and_the_latest_years_operating_income(self):
        # 1.1 made Growth revenue growth alone; 1.6 adds the direction of operating
        # income over the latest year. dGPOA must never return to it.
        from rankfield.metrics import METRICS
        operating_growth = [m["key"] for m in METRICS if m["factor"] == "growth"
                            and "operating" not in (m.get("not_for_segments") or [])]
        assert operating_growth == ["rev_growth", "op_inc_change"]

    def test_delta_gpoa_belongs_to_quality(self):
        from rankfield.metrics import METRICS_BY_KEY
        assert METRICS_BY_KEY["delta_gpoa"]["factor"] == "quality"

    def _score(self, rows):
        return score_segment(rows, weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                             min_cohort=8, coverage_threshold=0.7)

    def test_growth_factor_equals_the_revenue_growth_percentile(self):
        result = self._score(TestScoreSegmentEndToEnd()._rows())
        for r in result["scored"]:
            assert r["factors"]["growth"] == r["percentiles"]["rev_growth"]

    def test_delta_gpoa_is_not_roic_conditioned(self):
        result = self._score(TestScoreSegmentEndToEnd()._rows())
        below_hurdle = next(r for r in result["scored"] if r["ticker"] == "T0")  # ROIC 5%
        assert "below-hurdle" not in (below_hurdle["bases"]["delta_gpoa"] or "")
        assert "below-hurdle" in (below_hurdle["bases"]["rev_growth"] or "")

    def test_an_efficient_slow_grower_cannot_outscore_a_faster_grower_on_growth(self):
        rows = TestScoreSegmentEndToEnd()._rows()
        by = {r["ticker"]: r for r in rows}
        # Both clear the ROIC hurdle. T10 grows slower but has a huge efficiency
        # gain; T20 grows faster while its gross profitability ratio falls.
        by["T10"]["values"].update(rev_growth=0.105, delta_gpoa=0.40)
        by["T20"]["values"].update(rev_growth=0.161, delta_gpoa=-0.20)
        result = self._score(rows)
        scored = {r["ticker"]: r for r in result["scored"]}
        assert scored["T20"]["factors"]["growth"] > scored["T10"]["factors"]["growth"]


class TestSectorDeciles:
    """The default view is the top decile of each sector - so a company with no
    sector has no decile, rather than being the top of a cohort of itself."""

    @staticmethod
    def row(ticker, sector, composite):
        return {"ticker": ticker, "listing": {"sector": sector}, "composite": composite}

    def test_a_company_with_no_sector_gets_no_decile(self):
        rows = [self.row("BELFB", None, 45.1), self.row("GEF", None, 40.0)]
        assign_sector_deciles(rows)
        assert [r["sector_decile"] for r in rows] == [None, None]
        assert [r["sector_rank"] for r in rows] == [None, None]

    def test_an_empty_sector_label_counts_as_no_sector(self):
        rows = [self.row("X", "", 50.0)]
        assign_sector_deciles(rows)
        assert rows[0]["sector_decile"] is None

    def test_a_real_sector_still_gets_its_deciles(self):
        rows = [self.row(f"T{i}", "Technology", 100 - i) for i in range(20)]
        assign_sector_deciles(rows)
        assert rows[0]["sector_decile"] == 1 and rows[0]["sector_rank"] == 1
        assert rows[-1]["sector_decile"] == 10
        assert sum(1 for r in rows if r["sector_decile"] == 1) == 2


class TestWhatTheReturnHurdleApplluesTo:
    """2.1: the hurdle is about expanding while destroying value, which is a
    statement about revenue. The direction of profit is not conditioned on it."""

    @staticmethod
    def rows(roic):
        # a cohort wide enough to rank, all improving profit, all growing revenue
        out = []
        for i in range(12):
            out.append({
                "ticker": f"T{i}",
                "listing": {"sector": "Technology"},
                "segment": "operating",
                "missing": {},
                "values": {"roic": roic, "rev_growth": 0.05 * i, "op_inc_change": 0.05 * i,
                           "gpoa": 0.3, "earn_var": 0.1, "delta_gpoa": 0.01, "ebit_ev": 0.05,
                           "ebitda_ev": 0.06, "fcf_ev": 0.04, "debt_equity": 0.5,
                           "net_debt_ebitda": 1.0, "altman_z": 3.0},
            })
        return out

    def score(self, roic):
        res = score_segment(self.rows(roic), weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                            min_cohort=8, coverage_threshold=0.5)
        return {r["ticker"]: r for r in res["scored"]}

    def test_below_the_hurdle_revenue_growth_is_still_capped(self):
        best = self.score(0.02)["T11"]
        assert best["percentiles"]["rev_growth"] <= 50

    def test_below_the_hurdle_the_profit_change_keeps_its_own_percentile(self):
        # the whole point: shrinking a loss is not punished for the loss
        best = self.score(0.02)["T11"]
        assert best["percentiles"]["op_inc_change"] > 90

    def test_above_the_hurdle_nothing_changes(self):
        best = self.score(0.20)["T11"]
        assert best["percentiles"]["rev_growth"] > 90
        assert best["percentiles"]["op_inc_change"] > 90


class TestTheHurdleCeiling:
    """2.1: below the hurdle the score is capped, not mirrored."""

    @staticmethod
    def rows(growths, roic):
        return [{"ticker": f"T{i}", "listing": {"sector": "Technology"}, "segment": "operating",
                 "missing": {},
                 "values": {"roic": roic, "rev_growth": g, "op_inc_change": 0.0, "gpoa": 0.3,
                            "earn_var": 0.1, "delta_gpoa": 0.01, "ebit_ev": 0.05, "ebitda_ev": 0.06,
                            "fcf_ev": 0.04, "debt_equity": 0.5, "net_debt_ebitda": 1.0, "altman_z": 3.0}}
                for i, g in enumerate(growths)]

    def score(self, roic):
        rows = self.rows([0.01 * i for i in range(12)], roic)
        res = score_segment(rows, weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                            min_cohort=8, coverage_threshold=0.5)
        return {r["ticker"]: r["percentiles"]["rev_growth"] for r in res["scored"]}

    def test_the_fastest_grower_below_the_hurdle_lands_on_the_midpoint(self):
        assert self.score(0.02)["T11"] == 50.0

    def test_shrinking_is_still_not_rewarded(self):
        assert self.score(0.02)["T0"] == 0.0

    def test_nothing_below_the_hurdle_exceeds_the_midpoint(self):
        assert max(self.score(0.02).values()) == 50.0

    def test_above_the_hurdle_the_percentile_stands(self):
        assert self.score(0.20)["T11"] == 100.0


class TestPeerGroups:
    """Inside financials a bank, an insurer, a broker and an asset manager are
    ranked against their own kind, because their balance sheets differ by nature."""

    @staticmethod
    def group(industry, segment="financials", sector="Finance"):
        return peer_group({"sector": sector, "industry": industry}, segment)

    def test_each_kind_of_financial_business_gets_its_own_group(self):
        assert self.group("Major Banks") == "Banks & lenders"
        assert self.group("Savings Institutions") == "Banks & lenders"
        assert self.group("Finance: Consumer Services") == "Banks & lenders"
        assert self.group("Property-Casualty Insurers") == "Insurers"
        assert self.group("Life Insurance") == "Insurers"
        assert self.group("Investment Managers") == "Asset managers & other"

    def test_an_investment_banker_is_a_broker_not_a_bank(self):
        assert self.group("Investment Bankers/Brokers/Service") == "Brokers & capital markets"

    def test_outside_financials_the_peer_group_is_the_sector(self):
        assert self.group("Major Banks", segment="operating", sector="Technology") == "Technology"

    def test_no_sector_means_no_peer_group(self):
        assert peer_group({"sector": None, "industry": "Major Banks"}, "financials") is None

    def test_a_banks_leverage_is_ranked_against_banks_not_insurers(self):
        def row(ticker, industry, equity_assets):
            return {"ticker": ticker, "segment": "financials",
                    "listing": {"sector": "Finance", "industry": industry},
                    "values": {"equity_assets": equity_assets}, "missing": {}}
        banks = [row(f"B{i}", "Major Banks", 0.06 + i * 0.002) for i in range(12)]
        insurers = [row(f"I{i}", "Life Insurance", 0.20 + i * 0.01) for i in range(12)]
        scored = score_segment(
            banks + insurers, weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
            min_cohort=12, coverage_threshold=0.0, metric_applicability=0.0)
        by = {r["ticker"]: r for r in scored["scored"] + scored["insufficient"]}
        # The best bank is top of its own group despite holding far less equity
        # than the worst insurer.
        assert by["B11"]["percentiles"]["equity_assets"] > 90
        assert by["I0"]["percentiles"]["equity_assets"] < 10
        assert by["B11"]["peer_group"] == "Banks & lenders"
