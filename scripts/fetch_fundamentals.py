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

from rankfield.config import CACHE_DIR, CONFIG_DIR, DATA_DIR, ensure_dirs, load_settings, read_json, user_agent, write_json
from rankfield.facts import FactSet, merge_predecessor_facts
from rankfield.metrics import REVENUE, compute_metrics
from rankfield.providers import get_fundamentals_provider
from rankfield.util import last_day_of_prior_month, retry_failed


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
    successors = (read_json(CONFIG_DIR / "successors.json") or {}).get("successors", {})
    min_filings = settings["universe"]["min_quarters_filed"]
    tax_clamp = tuple(settings["scoring"]["effective_tax_clamp"])
    max_input_age = settings["scoring"]["max_input_age_days"]

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
                failures.append({"ticker": ticker, "reason": f"fetch failed: {exc}"[:200], "transient": True})
            return
        if not raw or not raw.get("facts"):
            with lock:
                failures.append({"ticker": ticker, "reason": "no XBRL facts on file"})
            return
        # A company that changed SEC registration number reads its predecessors' filings as its own.
        mapped = successors.get(listing["cik"])
        if mapped:
            try:
                older = [edgar.company_facts(cik, use_cache=not args.no_cache) for cik in mapped["predecessors"]]
            except Exception as exc:  # noqa: BLE001
                with lock:
                    failures.append({"ticker": ticker, "reason": f"predecessor fetch failed: {exc}"[:200], "transient": True})
                return
            raw = merge_predecessor_facts(raw, [o for o in older if o and o.get("facts")])
        fs = FactSet(raw, as_of, max_input_age_days=max_input_age)
        # A short record under an unmapped number may be a successor issuer: flag it for review.
        notice = False
        if not mapped and fs.quarters_filed < min_filings:
            try:
                notice = edgar.files_successor_notice(listing["cik"])
            except Exception:  # noqa: BLE001 - a courtesy check; its absence changes nothing
                notice = False
        result = compute_metrics(fs, market_cap=listing.get("market_cap"), tax_clamp=tax_clamp)
        revenue = fs.ttm(REVENUE)
        # A readable report older than the freshness rule: ask the filing index whether the
        # company has filed something newer that the structured data never received.
        newer = None
        latest_bs = result["provenance"].get("latest_balance_sheet")
        if latest_bs and (as_of - date.fromisoformat(latest_bs)).days > settings["universe"]["max_report_age_days"]:
            try:
                filing = edgar.newest_periodic_filing(listing["cik"], as_of)
            except Exception:  # noqa: BLE001 - the index is a courtesy; its absence changes nothing
                filing = None
            if filing and filing["report_date"] > latest_bs:
                newer = filing
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
            "newer_filing": newer,
            "predecessors": mapped["predecessors"] if mapped else [],
            "successor_notice": notice,
        }
        with lock:
            out[ticker] = record
            done[0] += 1
            if done[0] % 200 == 0:
                print(f"  ...{done[0]}/{len(listings)}", flush=True)

    print(f"fundamentals as of {as_of} for {len(listings)} companies")
    def run_pass(batch: list[dict]) -> None:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(work, batch))

    def failed_downloads() -> list[dict]:
        return [l for l in listings if any(f["ticker"] == l["ticker"] and f.get("transient") for f in failures)]

    def retry_pass(batch: list[dict]) -> None:
        # Drop the earlier failure record: the retry either succeeds or writes a new one.
        retried = {l["ticker"] for l in batch}
        failures[:] = [f for f in failures if f["ticker"] not in retried]
        run_pass(batch)

    run_pass(listings)
    retry_failed(listings, retry_pass, failed_downloads)

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
