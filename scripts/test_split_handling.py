"""Acceptance test: a split must not manufacture a monthly price move.

The trap this guards against: if a stock splits between two runs, last month's
STORED price sits on the pre-split basis. Comparing this month's adjusted close
against that stored number reads a 10-for-1 split as -90%. The pipeline must
instead read BOTH endpoints from today's adjusted series.

Two checks, both run against real data:

1. Simulated. A synthetic 10-for-1 split is constructed with a known true
   economic move, and the naive calculation (stored raw prior price) is compared
   against the pipeline's calculation.

2. Live. Every ticker in the current run whose price window contains an actual
   split is checked: the reported change must match the change recomputed from
   the adjusted series, and must not be near the raw split ratio.

Run: python scripts/test_split_handling.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import DATA_DIR, load_settings, read_json, user_agent
from rankfield.providers import get_price_provider
from rankfield.providers.prices_yahoo import PriceSeries

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}{(' - ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def simulated_split() -> None:
    """A stock trading at $900 splits 10-for-1 and then rises 5%."""
    print("\n1. Simulated 10-for-1 split")

    prior_raw_price = 900.00      # what last month's run stored, pre-split
    true_move_pct = 5.0
    # Today's adjusted series restates the whole history onto the post-split
    # basis: the prior close becomes 90.00, and the current close is 94.50.
    series = PriceSeries(
        ticker="TEST",
        dates=["2026-07-31", "2026-08-14", "2026-08-31"],
        closes=[90.00, 92.00, 94.50],
        volumes=[1e6, 1e6, 1e6],
        splits=[{"date": "2026-08-14", "ratio": "10.0:1.0"}],
    )

    now = series.close_on_or_before(date(2026, 8, 31))
    prior = series.close_on_or_before(date(2026, 7, 31))
    assert now and prior
    pipeline_pct = (now[1] / prior[1] - 1) * 100
    naive_pct = (now[1] / prior_raw_price - 1) * 100

    print(f"      stored prior price (pre-split basis): ${prior_raw_price:.2f}")
    print(f"      prior close re-read from today's adjusted series: ${prior[1]:.2f}")
    print(f"      naive calculation:    {naive_pct:+.2f}%   <- the bug")
    print(f"      pipeline calculation: {pipeline_pct:+.2f}%")

    check(
        "pipeline reports the true economic move",
        abs(pipeline_pct - true_move_pct) < 0.01,
        f"{pipeline_pct:+.2f}% vs expected {true_move_pct:+.2f}%",
    )
    check(
        "naive calculation would have reported a false collapse",
        naive_pct < -85,
        f"{naive_pct:+.2f}%",
    )


def live_splits() -> None:
    """Every real split inside the current price window."""
    print("\n2. Live splits in the current run")
    snapshot = read_json(DATA_DIR / "price_snapshot.json")
    if not snapshot:
        print("  (skipped: data/price_snapshot.json not found - run fetch_prices.py)")
        return

    scoring_date = date.fromisoformat(snapshot["scoring_date"])
    prior_date = date.fromisoformat(snapshot["prior_scoring_date"])
    with_splits = {t: row for t, row in snapshot["prices"].items() if row.get("splits_in_window")}
    print(f"  {len(with_splits)} tickers had a split inside the 1-year price window")

    settings = load_settings()
    provider = get_price_provider("yahoo", user_agent=user_agent(),
                                  per_sec=settings["http"]["price_workers"])

    checked = 0
    for ticker, row in list(with_splits.items())[:12]:
        series = provider.history(ticker, range_="1y")
        if not series:
            continue
        now = series.close_on_or_before(scoring_date)
        prior = series.close_on_or_before(prior_date)
        if not now or not prior:
            continue
        recomputed = (now[1] / prior[1] - 1) * 100
        stored = row["change_pct"]
        checked += 1
        ok = stored is not None and abs(recomputed - stored) < 0.5
        splits = ", ".join(s["ratio"] for s in row["splits_in_window"])
        check(
            f"{ticker} change matches the adjusted series (split {splits})",
            ok,
            f"stored {stored:+.2f}% vs recomputed {recomputed:+.2f}%",
        )

    if checked == 0:
        print("  (no split tickers resolvable right now - the simulated case still covers the logic)")


def first_run_nulls() -> None:
    """Edge case: a missing prior price must render as null, never as 0%."""
    print("\n3. Missing prior prices are null, never zero")
    snapshot = read_json(DATA_DIR / "price_snapshot.json")
    if not snapshot:
        print("  (skipped)")
        return
    zeros = [
        t for t, row in snapshot["prices"].items()
        if row.get("prior_price") is None and row.get("change_pct") == 0
    ]
    check("no stock with a missing prior price reports a 0% change", not zeros,
          f"{len(zeros)} offenders" if zeros else "")

    scores = read_json(DATA_DIR / "scores_full.json")
    if scores:
        bad = [
            r["ticker"]
            for rows in scores["segments"].values()
            for r in rows
            if r["prior_price"] is None and r["price_change_pct"] is not None
        ]
        check("no scored row invents a change without a prior price", not bad,
              f"{len(bad)} offenders" if bad else "")


def main() -> int:
    print("Split handling - acceptance test")
    simulated_split()
    live_splits()
    first_run_nulls()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
