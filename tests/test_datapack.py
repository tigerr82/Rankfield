import csv
import io
import zipfile

from rankfield.datapack import build_pack, unranked_record


def _row(ticker, rank, composite, **extra):
    row = {
        "ticker": ticker, "name": f"{ticker} Inc", "exchange": "NASDAQ", "cik": "1", "sector": "Tech",
        "peer_group": None, "rank": rank, "composite": composite, "price": 10.0, "price_change_pct": 1.0,
        "market_cap": 5e9, "coverage": 1.0, "fundamentals_asof": "2026-06-30", "form": "10-Q",
        "filed": "2026-07-30", "weights_version": "2.4", "rank_change": None, "composite_change": None,
        "is_new": False, "factors": {"quality": 1, "growth": 2, "valuation": 3, "health": 4},
        "metrics": {"roic": {"raw": 0.2, "pct": 90.0, "basis": "sector"}},
    }
    row.update(extra)
    return row


def _record(scoring_date, rows, run_date=None, backtested=False):
    return {
        "meta": {"scoring_date": scoring_date, "run_date": run_date or scoring_date, "weights_version": "2.4",
                 "counts": {"operating": len(rows), "insufficient": 3}},
        "backtested": backtested,
        "segments": {"operating": rows},
    }


CURRENT = {
    "metrics": [{"key": "roic", "label": "ROIC", "factor": "quality", "unit": "pct", "higher_better": True,
                 "formula": "x", "not_for_segments": ["banks"]}],
    "segments_meta": [{"key": "operating", "label": "Operating companies"}],
    "segments": {"operating": [_row("AAA", 1, 90, price=12.5, price_change_pct=3.0)]},
}


def _files(pack: bytes) -> dict[str, list[dict]]:
    z = zipfile.ZipFile(io.BytesIO(pack))
    return {n: list(csv.DictReader(io.StringIO(z.read(n).decode()))) for n in z.namelist() if n.endswith(".csv")}


def test_every_month_and_every_metric_is_in_the_pack():
    records = {"2026-09": _record("2026-09-30", [_row("AAA", 2, 80)]),
               "2026-10": _record("2026-10-31", [_row("AAA", 1, 90), _row("BBB", 2, 85)])}
    files = _files(build_pack(records, {}, CURRENT, "2026-11-02"))
    assert [r["month"] for r in files["months.csv"]] == ["2026-09", "2026-10"]
    assert len(files["scores_monthly.csv"]) == 3
    assert len(files["metrics_monthly.csv"]) == 3
    assert files["metrics_monthly.csv"][0]["factor"] == "quality"
    assert files["metrics_monthly.csv"][0]["sector_percentile"] == "90.0"


def test_latest_month_price_is_restated_but_older_months_keep_theirs():
    records = {"2026-09": _record("2026-09-30", [_row("AAA", 2, 80)]),
               "2026-10": _record("2026-10-31", [_row("AAA", 1, 90)])}
    scores = {r["month"]: r for r in _files(build_pack(records, {}, CURRENT, "x"))["scores_monthly.csv"]}
    assert scores["2026-09"]["price"] == "10.0"
    assert scores["2026-10"]["price"] == "12.5"


def test_months_rebuilt_after_the_fact_and_unrecorded_unranked_lists_are_labelled():
    records = {"2026-08": _record("2026-08-31", [_row("AAA", 2, 80)]),
               "2026-10": _record("2026-10-31", [_row("AAA", 1, 90)])}
    unranked = {"2026-10": {"entries": [{"ticker": "ZZZ", "name": "Z", "table": "operating",
                                         "kind": "insufficient_data", "reason": "too few metrics"}]}}
    files = _files(build_pack(records, unranked, CURRENT, "x"))
    months = {r["month"]: r for r in files["months.csv"]}
    assert months["2026-08"]["built"] == "rebuilt after the fact"
    assert months["2026-08"]["not_ranked_recorded"] == "not recorded"
    assert months["2026-10"]["not_ranked_recorded"] == "yes"
    assert files["not_ranked_monthly.csv"][0]["ticker"] == "ZZZ"


def test_unranked_record_collects_insufficient_data_and_exits():
    scores = {"meta": {"scoring_date": "2026-10-31"},
              "insufficient": [{"ticker": "I1", "name": "I", "segment": "operating", "reason": "few"}]}
    coverage = {"exits": [{"ticker": "E1", "name": "E", "segment": "banks", "kind": "unlisted", "reason": "gone"}]}
    kinds = {e["ticker"]: e["kind"] for e in unranked_record(scores, coverage)["entries"]}
    assert kinds == {"I1": "insufficient_data", "E1": "unlisted"}
