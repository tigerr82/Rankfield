"""Segmentation, composite renormalisation, deciles and the weight sweep."""
import pytest

from rankfield.scoring import (
    applicable_metrics,
    assign_sector_deciles,
    classify_segment,
    composite_of,
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

    def test_a_reit_is_a_financial(self):
        assert classify_segment(
            {"sector": "Real Estate", "industry": "Real Estate Investment Trusts"}, 1e9
        ) == "financials"

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

    def test_conditioning_lifts_sub_hurdle_names_off_the_bottom(self):
        # A company below the ROIC hurdle has its growth percentile inverted, so
        # the weakest grower among value-destroyers is no longer scored as the
        # worst name overall. This deliberately breaks the naive assumption that
        # the table is monotonic in the raw inputs.
        result = score_segment(self._rows(), weights=EQUAL, winsor=(5, 95), roic_hurdle=0.09,
                               min_cohort=8, coverage_threshold=0.7)
        by_ticker = {r["ticker"]: r for r in result["scored"]}
        # T0 has the worst raw growth of all, yet its Growth factor is high
        # because inversion rewards not expanding while destroying value.
        assert by_ticker["T0"]["factors"]["growth"] > by_ticker["T5"]["factors"]["growth"]
        assert by_ticker["T0"]["rank"] < by_ticker["T5"]["rank"]

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
        # the bottom of the cohort. Inversion turns its low growth percentile
        # into a high one - it is not expanding while destroying value.
        assert "inverted" in (by_ticker["T0"]["bases"]["rev_growth"] or "")
        # T29 clears the hurdle comfortably, so its percentile is used as-is.
        assert "inverted" not in (by_ticker["T29"]["bases"]["rev_growth"] or "")

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
