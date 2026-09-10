"""Stage 3 - fundamentals from SEC EDGAR, point-in-time as of the scoring date.

Writes data/fundamentals.json: for every company, the raw metric values, the
reason each unresolved metric failed, and the filing provenance (period end,
filed date, accession number, form) needed to reproduce or audit the score
later.

Run: python scripts/fetch_fundamentals.py [--limit N]
"""
from __future__ import annotations

import argparse
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import CACHE_DIR, DATA_DIR, ensure_dirs, load_settings, read_json, user_agent, write_json
from rankfield.facts import FactSet
from rankfield.metrics import REVENUE, compute_metrics
from rankfield.providers import get_fundamentals_provider
from rankfield.util import last_day_of_prior_month


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--no-cache", action="store_true", help="ignore the local companyfacts cache")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    ensure_dirs()
    settings = load_settings()
    as_of = date.fromisoformat(args.as_of) if args.as_of else last_day_of_prior_month(date.today())

    universe = read_json(DATA_DIR / "universe.json")
    if not universe:
        print("data/universe.json missing - run scripts/fetch_universe.py first", file=sys.stderr)
        return 1
    listings = universe["listings"][: args.limit] if args.limit else universe["listings"]

    edgar = get_fundamentals_provider(
        "edgar",
        user_agent=user_agent(),
        cache_dir=CACHE_DIR / "facts",
        per_sec=settings["http"]["sec_rate_limit_per_sec"],
    )
    tax_clamp = tuple(settings["scoring"]["effective_tax_clamp"])

    out: dict[str, dict] = {}
    failures: list[dict] = []
    lock = threading.Lock()
    done = [0]

    def work(listing: dict) -> None:
        ticker = listing["ticker"]
        try:
            raw = edgar.company_facts(listing["cik"], use_cache=not args.no_cache)
        except Exception as exc:  # noqa: BLE001
            with lock:
                failures.append({"ticker": ticker, "reason": f"fetch failed: {exc}"[:200]})
            return
        if not raw or not raw.get("facts"):
            with lock:
                failures.append({"ticker": ticker, "reason": "no XBRL facts on file"})
            return
        fs = FactSet(raw, as_of)
        result = compute_metrics(fs, market_cap=listing.get("market_cap"), tax_clamp=tax_clamp)
        revenue = fs.ttm(REVENUE)
        record = {
            "ticker": ticker,
            "cik": listing["cik"],
            "entity_name": fs.entity,
            "values": result["values"],
            "missing": result["missing"],
            "provenance": result["provenance"],
            "notes": result["notes"],
            "revenue_ttm": (revenue or {}).get("val"),
            "quarters_filed": fs.quarters_filed,
            "files_domestic_forms": fs.files_domestic_forms,
            "forms": sorted(fs.forms),
        }
        with lock:
            out[ticker] = record
            done[0] += 1
            if done[0] % 200 == 0:
                print(f"  ...{done[0]}/{len(listings)}", flush=True)

    print(f"fundamentals as of {as_of} for {len(listings)} companies")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, listings))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": edgar.name,
        "source_licence": edgar.licence,
        "as_of": as_of.isoformat(),
        "requested": len(listings),
        "resolved": len(out),
        "failures": failures,
        "companies": out,
    }
    path = write_json(DATA_DIR / "fundamentals.json", payload, compact=True)

    metric_hits: dict[str, int] = {}
    for record in out.values():
        for key, value in record["values"].items():
            if value is not None:
                metric_hits[key] = metric_hits.get(key, 0) + 1
    print(f"fundamentals -> {path}")
    print(f"  {len(out)} resolved, {len(failures)} failed")
    print("  metric resolution across the universe:")
    for key, hits in sorted(metric_hits.items(), key=lambda kv: -kv[1]):
        print(f"    {key:<16} {hits:>5} / {len(out)}  ({hits / max(len(out), 1):.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
