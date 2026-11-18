"""Adds the research measures to months recorded before they were measured.

For every ranked company of every stored month that has no `research` entry, computes
momentum, net payout yield and accruals as of that month's scoring date - filings filed on or
before it (point-in-time, like the scores themselves), the market cap stored in the record,
and the price series cut at the scoring date - and writes them under `research`.

Nothing else in a record is touched: no rank, score, price or weight. The script checks this
before writing a file and refuses if anything but `research` would change.

Run: RANKFIELD_USER_AGENT="Name email" python scripts/backfill_research.py [--months 2026-08 ...]
"""
from __future__ import annotations

import argparse
import copy
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import CACHE_DIR, CONFIG_DIR, HISTORY_DIR, load_settings, read_json, user_agent, write_json
from rankfield.facts import FactSet, merge_predecessor_facts
from rankfield.providers import get_fundamentals_provider, get_price_provider
from rankfield.shadow import momentum, shadow_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", nargs="*", default=None, help="e.g. 2026-08 2026-09 (default: all without research)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = load_settings()

    files = sorted(HISTORY_DIR.glob("scores_*.json"))
    records = {}
    for path in files:
        month = path.stem.removeprefix("scores_")
        if args.months and month not in args.months:
            continue
        rec = read_json(path)
        rows = [r for seg in rec["segments"].values() for r in seg]
        if any("research" not in r for r in rows):
            records[month] = (path, rec)
    if not records:
        print("nothing to backfill")
        return 0

    todo: dict[str, dict] = {}   # ticker -> {cik}
    for _, rec in records.values():
        for seg in rec["segments"].values():
            for r in seg:
                todo.setdefault(r["ticker"], {"cik": r["cik"]})
    print(f"{len(records)} months, {len(todo)} companies")

    edgar = get_fundamentals_provider("edgar", user_agent=user_agent(), cache_dir=CACHE_DIR / "facts",
                                      per_sec=settings["http"]["sec_rate_limit_per_sec"])
    prices = get_price_provider("yahoo", user_agent=user_agent(), per_sec=settings["http"]["price_workers"] * 1.5)
    successors = (read_json(CONFIG_DIR / "successors.json") or {}).get("successors", {})
    facts_raw: dict[str, dict] = {}
    series_by: dict[str, object] = {}
    lock = threading.Lock()

    def load(item) -> None:
        ticker, info = item
        raw = None
        try:
            raw = edgar.company_facts(info["cik"])
            mapped = successors.get(info["cik"])
            if raw and raw.get("facts") and mapped:
                older = [edgar.company_facts(c) for c in mapped["predecessors"]]
                raw = merge_predecessor_facts(raw, [o for o in older if o and o.get("facts")])
        except Exception as exc:  # noqa: BLE001 - a company that fails stays empty, and is counted
            print(f"  facts failed for {ticker}: {str(exc)[:80]}")
        try:
            series = prices.history(ticker, range_="2y")
        except Exception as exc:  # noqa: BLE001
            print(f"  prices failed for {ticker}: {str(exc)[:80]}")
            series = None
        with lock:
            facts_raw[ticker] = raw if raw and raw.get("facts") else None
            series_by[ticker] = series

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(load, todo.items()))
    print(f"loaded facts for {sum(1 for v in facts_raw.values() if v)} and prices for "
          f"{sum(1 for v in series_by.values() if v)} of {len(todo)}")

    max_age = settings["scoring"]["max_input_age_days"]
    for month, (path, rec) in sorted(records.items()):
        scoring = date.fromisoformat(rec["meta"]["scoring_date"])
        before = copy.deepcopy(rec)
        filled = {"momentum_12_1": 0, "momentum_6_1": 0, "net_payout_yield": 0, "accruals": 0}
        total = 0
        for seg in rec["segments"].values():
            for r in seg:
                if "research" in r:
                    continue
                total += 1
                raw, series = facts_raw.get(r["ticker"]), series_by.get(r["ticker"])
                values = {"net_payout_yield": None, "accruals": None}
                if raw:
                    values = shadow_metrics(FactSet(raw, scoring, max_input_age_days=max_age),
                                            r.get("market_cap"))["values"]
                values["momentum_12_1"] = momentum(series, scoring, 12) if series else None
                values["momentum_6_1"] = momentum(series, scoring, 6) if series else None
                r["research"] = values
                for k in filled:
                    filled[k] += values.get(k) is not None
        # Only the added key may differ: strip it and compare every row with the untouched copy.
        def bare(record):
            return {t: [{k: v for k, v in r.items() if k != "research"} for r in rows]
                    for t, rows in record["segments"].items()}
        if bare(rec) != bare(before) or rec["meta"] != before["meta"]:
            print(f"{month}: a field other than research changed - refusing to write")
            return 1
        print(f"{month}: {total} companies; filled " + ", ".join(f"{k} {v}" for k, v in filled.items()))
        if not args.dry_run:
            write_json(path, rec, compact=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
