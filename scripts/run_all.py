"""Run the whole monthly pipeline in order.

    universe -> prices -> fundamentals -> scores -> site payloads

Each stage is a standalone script and can be re-run on its own; this is the
convenience wrapper for a local run.

Run: python scripts/run_all.py [--as-of YYYY-MM-DD] [--limit N]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def stage(name: str, args: list[str]) -> float:
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    started = time.time()
    result = subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]], check=False)
    if result.returncode != 0:
        print(f"\n{name} failed with exit code {result.returncode}", file=sys.stderr)
        raise SystemExit(result.returncode)
    return time.time() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None, help="scoring date override (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=0, help="debug: cap the universe size")
    parser.add_argument("--force-history", action="store_true",
                        help="overwrite this month's history file (normally refused)")
    args = parser.parse_args()

    as_of = ["--as-of", args.as_of] if args.as_of else []
    limit = ["--limit", str(args.limit)] if args.limit else []

    timings = {
        "1/5 universe": stage("1/5  Universe, sector and market cap", ["fetch_universe.py", *limit]),
        "2/5 prices": stage("2/5  Adjusted closes and liquidity", ["fetch_prices.py", *as_of, *limit]),
        "3/5 fundamentals": stage("3/5  EDGAR fundamentals (point-in-time)", ["fetch_fundamentals.py", *as_of, *limit]),
        "4/5 scores": stage("4/5  Scoring, history and coverage report",
                            ["compute_scores.py", *as_of, *(["--force-history"] if args.force_history else [])]),
        "5/5 payloads": stage("5/5  Site payloads", ["build_json.py"]),
    }

    print(f"\n{'=' * 70}\nDone.")
    for name, seconds in timings.items():
        print(f"  {name:<20} {seconds:6.1f}s")
    print(f"  {'total':<20} {sum(timings.values()):6.1f}s")
    print("\nNext: cd site && npm run dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
