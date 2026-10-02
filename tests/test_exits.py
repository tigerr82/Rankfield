"""Every company that leaves the ranking is traced to a stage, not just counted."""
from rankfield.exits import build_exits

PRIOR = {t: {"name": t, "sector": "X", "segment": "operating", "rank": i}
         for i, t in enumerate(["STAYS", "FLOOR", "EXCL", "THIN", "CLASSB", "FILER", "GONE"], 1)}
UNIVERSE = {
    "market_cap_floor_usd": 1_000_000_000,
    "below_floor": {"FLOOR": 991_000_000},
    "dropped_share_classes": [{"kept": "CLASSA", "dropped": "CLASSB", "company": "c"}],
    "unmatched_tickers": ["FILER"],
}


def exits():
    return {e["ticker"]: e for e in build_exits(
        PRIOR, {"STAYS"},
        excluded=[{"ticker": "EXCL", "stage": "liquidity", "reason": "volume too low"}],
        insufficient=[{"ticker": "THIN", "reason": "scored on 3 of 11 metrics"}],
        universe=UNIVERSE,
    )}


def test_a_company_still_scored_is_not_an_exit():
    assert "STAYS" not in exits()


def test_each_exit_is_traced_to_the_stage_that_removed_it():
    got = exits()
    assert got["FLOOR"]["kind"] == "market_cap_floor"
    assert "$991M" in got["FLOOR"]["reason"] and "$1B" in got["FLOOR"]["reason"]
    assert got["EXCL"]["kind"] == "excluded" and "volume too low" in got["EXCL"]["reason"]
    assert got["THIN"]["kind"] == "insufficient_data"
    assert got["CLASSB"]["kind"] == "share_class" and "CLASSA" in got["CLASSB"]["reason"]
    assert got["FILER"]["kind"] == "no_sec_match"


def test_no_trace_anywhere_is_said_plainly_rather_than_guessed():
    assert exits()["GONE"]["kind"] == "unlisted"


def test_an_earlier_stage_wins_over_a_later_one():
    got = {e["ticker"]: e for e in build_exits(
        {"BOTH": {"name": "b", "rank": 1}}, set(),
        excluded=[{"ticker": "BOTH", "stage": "liquidity", "reason": "r"}],
        insufficient=[{"ticker": "BOTH", "reason": "r2"}],
        universe={"below_floor": {"BOTH": 1.0}},
    )}
    assert got["BOTH"]["kind"] == "excluded"
