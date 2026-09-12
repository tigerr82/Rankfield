"""The scoring primitives.

`percentile_ranks` shipped inverted once - a -47.8% ROIC scored 97.7 and Rivian
ranked first. These tests exist so that specific failure, and its neighbours,
cannot come back silently.
"""
from datetime import date

import pytest

from rankfield.util import (
    last_day_of_prior_month,
    mean,
    parse_iso,
    percentile_of,
    percentile_ranks,
    safe_div,
    shift_months,
    stdev,
    winsorize,
)


class TestPercentileRanks:
    def test_higher_better_puts_the_largest_value_first(self):
        # The regression: the best value must score 100, not 0.
        assert percentile_ranks([1, 2, 3, 5], higher_better=True) == [0.0, 33.3, 66.7, 100.0]

    def test_lower_better_puts_the_smallest_value_first(self):
        # Debt/equity, earnings variability: low is good.
        assert percentile_ranks([1, 2, 3, 5], higher_better=False) == [100.0, 66.7, 33.3, 0.0]

    def test_negative_values_rank_below_positive_ones(self):
        # A loss-making company must not score like a profitable one.
        ranks = percentile_ranks([-0.48, 0.05, 0.20, 0.35], higher_better=True)
        assert ranks[0] == 0.0
        assert ranks[-1] == 100.0

    def test_missing_values_stay_missing(self):
        ranks = percentile_ranks([1, None, 3], higher_better=True)
        assert ranks[1] is None
        assert ranks == [0.0, None, 100.0]

    def test_ties_share_the_average_rank(self):
        ranks = percentile_ranks([5, 5, 1], higher_better=True)
        assert ranks[0] == ranks[1]
        assert ranks[2] < ranks[0]

    def test_all_missing_returns_all_missing(self):
        assert percentile_ranks([None, None], higher_better=True) == [None, None]

    def test_single_value_scores_the_midpoint(self):
        # One observation carries no ranking information; 50 is the only
        # defensible answer, and it must not be 0 or 100.
        assert percentile_ranks([7], higher_better=True) == [50.0]

    def test_every_rank_is_within_bounds(self):
        values = [3, -1, 99, 0, 42, None, 7]
        for higher in (True, False):
            for r in percentile_ranks(values, higher_better=higher):
                assert r is None or 0.0 <= r <= 100.0

    def test_direction_is_a_mirror(self):
        values = [1.0, 4.0, 9.0, 11.0]
        up = percentile_ranks(values, higher_better=True)
        down = percentile_ranks(values, higher_better=False)
        assert up == list(reversed(down))


class TestWinsorize:
    def test_clips_extremes_to_the_percentile_bounds(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1000]
        clipped = winsorize(values, 5, 95)
        assert max(clipped) < 1000
        assert min(clipped) >= 1

    def test_preserves_missing_values(self):
        clipped = winsorize([1, None, 3, 500], 5, 95)
        assert clipped[1] is None

    def test_small_samples_pass_through_untouched(self):
        # Fewer than three observations cannot define a 5th/95th percentile.
        assert winsorize([5, 9], 5, 95) == [5, 9]

    def test_all_missing_is_not_an_error(self):
        assert winsorize([None, None], 5, 95) == [None, None]

    def test_does_not_change_the_ordering(self):
        values = [10, -50, 3, 7, 900, 4]
        clipped = winsorize(values, 5, 95)
        order_before = sorted(range(len(values)), key=lambda i: values[i])
        order_after = sorted(range(len(clipped)), key=lambda i: clipped[i])
        assert order_before == order_after


class TestPercentileOf:
    def test_median_of_a_simple_series(self):
        assert percentile_of([1, 2, 3, 4, 5], 50) == 3

    def test_ignores_missing_values(self):
        assert percentile_of([1, None, 3], 50) == 2


class TestSafeDiv:
    @pytest.mark.parametrize("num,den", [(1, 0), (1, None), (None, 1), (None, None), (0, 0)])
    def test_returns_none_rather_than_zero_or_raising(self, num, den):
        # "Zero or missing denominator -> null, never zero" - a zero here would
        # become a real score and silently punish the company.
        assert safe_div(num, den) is None

    def test_divides_normally(self):
        assert safe_div(10, 4) == 2.5

    def test_keeps_a_true_negative(self):
        assert safe_div(-10, 4) == -2.5


class TestDates:
    def test_scoring_date_is_the_last_day_of_the_prior_month(self):
        assert last_day_of_prior_month(date(2026, 9, 2)) == date(2026, 8, 31)
        assert last_day_of_prior_month(date(2026, 1, 2)) == date(2025, 12, 31)
        assert last_day_of_prior_month(date(2026, 3, 2)) == date(2026, 2, 28)

    def test_handles_a_leap_year(self):
        assert last_day_of_prior_month(date(2024, 3, 5)) == date(2024, 2, 29)

    def test_shift_months_clamps_to_a_valid_day(self):
        assert shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
        assert shift_months(date(2026, 1, 15), 13) == date(2027, 2, 15)

    def test_parse_iso_tolerates_a_timestamp_suffix(self):
        assert parse_iso("2026-08-31T12:00:00Z") == date(2026, 8, 31)


class TestStats:
    def test_mean_and_stdev_ignore_missing(self):
        assert mean([1, None, 3]) == 2
        assert stdev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.138, abs=1e-3)

    def test_stdev_needs_two_observations(self):
        assert stdev([5]) is None

    def test_mean_of_nothing_is_none(self):
        assert mean([]) is None
