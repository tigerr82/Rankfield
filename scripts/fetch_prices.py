"""Stage 2 - one adjusted close per stock per run, plus the prior month's.

v1 deliberately does not backfill price history: with no charts to draw, the
scoring run needs exactly two endpoints and a liquidity measure. Both endpoints
are read from TODAY'S adjusted series, which is the whole point - a stock that
split since last month has a stored prior price on the old basis, and comparing
against it would read a 10-for-1 split as -90%.

Run: python scripts/fetch_prices.py
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import DATA_DIR, ensure_dirs, load_settings, read_json, user_agent, write_json
from rankfield.providers import get_price_provider
from rankfield.util import last_day_of_prior_month


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="yahoo", choices=["yahoo", "stooq"])
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    ensure_dirs()
    settings = load_settings()
    scoring_date = date.fromisoformat(args.as_of) if args.as_of else last_day_of_prior_month(date.today())
    prior_scoring_date = last_day_of_prior_month(scoring_date.replace(day=1))

    universe = read_json(DATA_DIR / "universe.json")
    if not universe:
        print("data/universe.json missing - run scripts/fetch_universe.py first", file=sys.stderr)
        return 1
    listings = universe["listings"][: args.limit] if args.limit else universe["listings"]

    provider = get_price_provider(
        args.provider, user_agent=user_agent(), per_sec=settings["http"]["price_workers"] * 1.5
    )
    review_threshold = settings["sanity"]["price_move_review_pct"] / 100.0

    snapshot: dict[str, dict] = {}
    failures: list[dict] = []
    review: list[dict] = []

    def work(listing: dict) -> None:
        ticker = listing["ticker"]
        try:
            series = provider.history(ticker, range_="1y")
        except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
            failures.append({"ticker": ticker, "reason": str(exc)[:200]})
            return
        if not series:
            failures.append({"ticker": ticker, "reason": "no price series returned"})
            return
        now = series.close_on_or_before(scoring_date)
        prior = series.close_on_or_before(prior_scoring_date)
        if not now:
            failures.append({"ticker": ticker, "reason": f"no close on or before {scoring_date}"})
            return
        change_pct = None
        if prior and prior[1]:
            change_pct = (now[1] / prior[1] - 1) * 100
            if abs(change_pct) > review_threshold * 100:
                review.append(
                    {
                        "ticker": ticker,
                        "change_pct": round(change_pct, 2),
                        "splits_in_window": series.splits,
                        "note": "monthly move beyond the review threshold - check for a corporate action",
                    }
                )
        snapshot[ticker] = {
            "price_date": now[0],
            "price": round(now[1], 4),
            "prior_price_date": prior[0] if prior else None,
            "prior_price": round(prior[1], 4) if prior else None,
            "change_pct": round(change_pct, 4) if change_pct is not None else None,
            "change_abs": round(now[1] - prior[1], 4) if prior else None,
            "adv_dollar": series.avg_dollar_volume(63),
            "splits_in_window": series.splits,
        }

    with ThreadPoolExecutor(max_workers=settings["http"]["price_workers"]) as pool:
        list(pool.map(work, listings))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider.name,
        "provider_licence": getattr(provider, "licence", "unknown"),
        "scoring_date": scoring_date.isoformat(),
        "prior_scoring_date": prior_scoring_date.isoformat(),
        "requested": len(listings),
        "resolved": len(snapshot),
        "failures": failures,
        "review": sorted(review, key=lambda r: -abs(r["change_pct"])),
        "prices": snapshot,
    }
    path = write_json(DATA_DIR / "price_snapshot.json", payload, compact=True)
    print(f"prices -> {path}")
    print(f"  {len(snapshot)} of {len(listings)} resolved via {provider.name}")
    print(f"  scoring date {scoring_date}, prior {prior_scoring_date}")
    print(f"  {len(failures)} failures, {len(review)} flagged for corporate-action review")
    for row in payload["review"][:8]:
        print(f"    {row['ticker']:<6} {row['change_pct']:+8.1f}%  splits={row['splits_in_window'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
