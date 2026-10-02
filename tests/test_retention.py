"""The eligibility floors are asymmetric: easy to stay, hard to join."""
import json

from rankfield.retention import clears, previous_scored
from datetime import date

FLOOR = 1_000_000_000


def test_above_the_floor_always_clears():
    assert clears(FLOOR, FLOOR, was_scored=False, ratio=0.8)


def test_a_ranked_company_keeps_its_place_until_clearly_below():
    assert clears(850_000_000, FLOOR, was_scored=True, ratio=0.8)
    assert clears(800_000_000, FLOOR, was_scored=True, ratio=0.8)
    assert not clears(799_000_000, FLOOR, was_scored=True, ratio=0.8)


def test_a_newcomer_gets_no_allowance():
    assert not clears(999_000_000, FLOOR, was_scored=False, ratio=0.8)


def test_an_unknown_value_never_clears():
    assert not clears(None, FLOOR, was_scored=True, ratio=0.8)


def test_last_months_scored_set_reads_the_month_before(tmp_path):
    (tmp_path / "scores_2026-08.json").write_text(
        json.dumps({"segments": {"operating": [{"ticker": "AAA"}], "reits": [{"ticker": "BBB"}]}}))
    assert previous_scored(tmp_path, date(2026, 9, 30)) == {"AAA", "BBB"}
    assert previous_scored(tmp_path, date(2026, 8, 31)) == set()
